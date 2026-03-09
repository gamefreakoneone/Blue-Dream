import asyncio
import datetime
import os

from motor.motor_asyncio import AsyncIOMotorClient

from .audio_transcribe import Audio_agent
from .memory_schema import memory_event_to_mongo, new_memory_event
from .timezone_utils import now_local
from .video_agent import Video_Agent

# So video is recorded. Then it is passed to the consolidator agent.
# The consolidator agent will call the video_agent, to describe the video, and the audio_agent which will then transcribe the audio
# After the video description and audio transcript has been received, we will create a state object which will contain the following:
# 1. Unique ascending ID
# 2. Time and Date of recording
# 3. Room Number
# 4. Video Description
# 5. Audio Transcript
# 6. Last screenshot
# 7. Video Path

# This state object will be stored in a NoSQL database. Which will then be interacted with the jeeves agent (main agent)


# MongoDB setup
def get_mongodb_client(connection_string: str = None):
    if connection_string is None:
        connection_string = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    return AsyncIOMotorClient(connection_string)


async def consolidator_agent(
    video_path: str,
    audio_path: str,
    screenshot_path: str,
    room_number: int,
    timestamp: datetime.datetime = None,
    mongo_connection_string: str = None,
):
    if timestamp is None:
        timestamp = now_local()

    mongodb_client = get_mongodb_client(mongo_connection_string)
    db = mongodb_client.dementia_assistance  # This is initalizing the database
    collection = db.events  # This is initializing the tables within the database

    # TODO : Create also a VectorDB here for semantic search. (Future task)

    # Now here we will call the video agent for the video description of the events in the room and the audio agent for the audio transcript
    video_agent = Video_Agent()
    loop = asyncio.get_running_loop()

    video_details = await loop.run_in_executor(
        None, video_agent.video_description, video_path
    )

    audio_agent = Audio_agent()
    audio_transcript = await loop.run_in_executor(
        None, audio_agent.transcribe_audio, audio_path
    )

    # we will now create a JSON object which is going to be stored in the database

    event = new_memory_event(
        timestamp=timestamp,
        room_number=room_number,
        video_description=video_details.video_description,
        room_objects=video_details.room_objects,
        audio_transcript=audio_transcript,
        screenshot_path=screenshot_path,
        video_path=video_path,
        audio_path=audio_path,
    )
    document = memory_event_to_mongo(event)
    result = await collection.insert_one(document)
    print(f"Inserted document with ID: {result.inserted_id}")

    mongodb_client.close()
    return result.inserted_id
