"""
Video Processing Queue Module

Producer-Consumer pattern for processing recorded videos asynchronously.
The camera feed (producer) adds video tasks to a queue, and a background
consumer thread processes them through the consolidator agent.
"""

import queue
import threading
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Blue_dream_agents.consolidator import consolidator_agent


@dataclass
class VideoTask:
    """Represents a video processing task to be queued."""

    video_path: str
    audio_path: str
    screenshot_path: str
    room_number: int
    timestamp: datetime


class VideoProcessingQueue:
    """
    Thread-safe queue for processing videos through the consolidator agent.

    Usage:
        queue = VideoProcessingQueue()
        queue.start()  # Start the consumer thread

        # Add tasks from the camera feed
        queue.add_task(video_path, audio_path, screenshot_path, room_number, timestamp)

        # When shutting down
        queue.stop()  # Waits for all tasks to complete
    """

    def __init__(self):
        self._queue: queue.Queue[Optional[VideoTask]] = queue.Queue()
        self._consumer_thread: Optional[threading.Thread] = None
        self._running = False
        self._total_processed = 0
        self._total_errors = 0
        self._lock = threading.Lock() 

    def start(self):
        """Start the consumer thread."""
        if self._running:
            print("Warning: VideoProcessingQueue is already running")
            return

        self._running = True
        self._consumer_thread = threading.Thread(
            target=self._consumer_loop, daemon=True
        )
        self._consumer_thread.start()
        print("Video processing queue started")

    def stop(self):
        """Stop the consumer thread and wait for all tasks to complete."""
        if not self._running:
            return

        # Show remaining tasks
        remaining = self._queue.qsize()
        if remaining > 0:
            print(f"\nShutting down... {remaining} videos remaining in queue")

        # Signal the consumer to stop by adding None to the queue
        self._queue.put(None)

        # Wait for consumer thread to finish
        if self._consumer_thread is not None:
            self._consumer_thread.join()

        self._running = False
        print(
            f"Video processing complete. Processed: {self._total_processed}, Errors: {self._total_errors}"
        )

    def add_task(
        self,
        video_path: str,
        audio_path: str,
        screenshot_path: str,
        room_number: int,
        timestamp: datetime,
    ):
        """Add a video processing task to the queue."""
        if not self._running:
            print("Warning: Cannot add task - queue is not running")
            return

        task = VideoTask(
            video_path=video_path,
            audio_path=audio_path,
            screenshot_path=screenshot_path,
            room_number=room_number,
            timestamp=timestamp,
        )
        self._queue.put(task)
        print(f"Added video task to queue: {os.path.basename(video_path)}")

    def _consumer_loop(self):
        """Consumer loop that processes tasks from the queue using a persistent event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while True:
                task = self._queue.get()

                # None is the signal to stop
                if task is None:
                    self._queue.task_done()
                    break

                # Show progress
                remaining = self._queue.qsize()
                with self._lock:
                    current_num = self._total_processed + self._total_errors + 1

                print(f"\nProcessing video {current_num} ({remaining} more in queue)...")
                print(f"  Video: {os.path.basename(task.video_path)}")

                try:
                    # Run the async consolidator_agent in the persistent event loop
                    loop.run_until_complete(
                        consolidator_agent(
                            video_path=task.video_path,
                            audio_path=task.audio_path,
                            screenshot_path=task.screenshot_path,
                            room_number=task.room_number,
                            timestamp=task.timestamp,
                        )
                    )

                    with self._lock:
                        self._total_processed += 1
                    print(
                        f"  Successfully processed: {os.path.basename(task.video_path)}"
                    )

                except Exception as e:
                    with self._lock:
                        self._total_errors += 1
                    print(f"  Error processing {os.path.basename(task.video_path)}: {e}")

                finally:
                    self._queue.task_done()
        finally:
            loop.close()

    @property
    def pending_count(self) -> int:
        """Return the number of pending tasks in the queue."""
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        """Return whether the queue is running."""
        return self._running
