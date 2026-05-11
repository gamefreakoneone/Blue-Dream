# planning on using the Gemini API for this one

from google import genai
import os
import time
from pydantic import BaseModel, Field

try:
    from .llm.settings import load_project_env
except ImportError:
    from llm.settings import load_project_env

load_project_env()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class video_results(BaseModel):
    video_description: str = Field(
        "Detailed description of the monitored patient's actions in the video. If another person is explicitly visible, preserve that separate identity."
    )
    room_objects: list[str] = Field(
        "List of objects present in the video which the user interacted with, or have added to environment and is still in the room and not removed from the scene."
    )


class Video_Agent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        configured_model = os.getenv("GEMINI_VIDEO_MODEL", "gemini-2.5-flash").strip()
        self.model_candidates = []
        for candidate in (
            configured_model,
            f"models/{configured_model}" if not configured_model.startswith("models/") else configured_model.split("/", 1)[1],
        ):
            if candidate and candidate not in self.model_candidates:
                self.model_candidates.append(candidate)

    def _upload_video(self, video_path):
        myfile = self.client.files.upload(file=video_path)
        print("Processing video...")
        while myfile.state == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(1)
            myfile = self.client.files.get(name=myfile.name)
        if myfile.state == "FAILED":
            raise Exception("File processing failed.")
        print("\nFile is ready!")
        return myfile

    def _generate_video_summary(self, myfile):
        last_error = None
        for model_name in self.model_candidates:
            try:
                return self.client.models.generate_content(
                    model=model_name,
                    contents=[
                        myfile,
                        """
                    You are a dementia assistance agent. Your job is to monitor the actions of the patient in the video and describe their actions in detail. If only one unlabeled person is visible, refer to that person as the patient. If another person is explicitly visible, preserve that separate identity. If the patient is interacting with the environment,
                    describe the objects they are interacting with. Once the user is done using the object and deposits back in the environment, describe the new location of the object relative to the environment.
                    Also describe if the patient has added new objects to the environment (and their respective location wrt to the environment) or removed objects from the environment.
                    You will write these results in the video description, and the objects that the user interacted with in the room in the room_objects list. 
                    Objects that have been removed from the environment will not be in the room_objects list.

                    Output Example:
                    {
                        "video_description": "The patient, wearing a blue and yellow hoodie, blue jeans, and black headphones, is initially standing. 
                        They reach down to a brown office chair and pick up a black smartphone. The patient then sits on the brown office chair, holding the 
                        smartphone and looking at its screen, appearing to speak or react to its content. After a few moments, they place the black smartphone and the headphones
                        on the white bed, next to a white baseball cap. Immediately after, the patient picks up the white baseball cap from the bed, stands up, 
                        and walks out of the frame.",
                        "room_objects": ["headphones", "black smartphone"]
                    }
                    """,
                    ],
                    config={
                        "response_mime_type": "application/json",
                        "response_json_schema": video_results.model_json_schema(),
                    },
                )
            except Exception as exc:
                last_error = exc
                print(f"Gemini video generation failed with model {model_name}: {exc}")

        raise RuntimeError(
            f"Gemini video generation failed for all candidate models {self.model_candidates}: {last_error}"
        )

    def video_description(self, video_path):
        myfile = self._upload_video(video_path)
        response = self._generate_video_summary(myfile)
        result = video_results.model_validate_json(response.text)
        return result


if __name__ == "__main__":
    test_agent = Video_Agent()
    print(
        test_agent.video_description(
            r"C:\Users\amogh\Desktop\Blue-Dream\Storage\video_recordings\camera_1\camera_1_2026-01-15_16-31-06.mp4"
        )
    )
