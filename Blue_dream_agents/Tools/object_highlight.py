import os
import time 
import base64
from openai import OpenAI
try:
    from ..llm.settings import load_project_env
except ImportError:
    from llm.settings import load_project_env

load_project_env()


class Object_Highlight:
    def __init__(self):
        self.client = OpenAI()
    
    def highlight_objects(self, image_path , object_name , video_description):
        prompt = """
        You are tasked with highlighting the following object in the image: {object_name} by drawing a red circle around it. 
        The position of the object in the environment is described as : {video_description}.
        """
        image = open(image_path, "rb")
        img = self.client.images.edit(
            model="gpt-image-1.5",
            prompt= prompt,
            image= [open(image_path, "rb")]
        )
        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        with open("output.png", "wb") as f:
            f.write(image_bytes)


