from google import genai
import os
import time
from dotenv import load_dotenv

# Initialize client with your API key
load_dotenv()
client = genai.Client(api_key=os.getenv("API_KEY"))

# 1. Upload the video file
print("Uploading file...")
myfile = client.files.upload(file=r"C:\Users\amogh\Downloads\Hi Me In 10 Years.publer.com.mp4")
print(f"File uploaded: {myfile.name}")

# 2. Wait for the file to be processed and become ACTIVE
while myfile.state.name == "PROCESSING":
    print("File is processing. Waiting...")
    time.sleep(10)  # Wait for 10 seconds before checking again
    # Get the latest status of the file
    myfile = client.files.get(name=myfile.name)

# 3. Check if processing failed
if myfile.state.name == "FAILED":
    raise ValueError("File processing failed.")

print(f"File is now {myfile.state.name} and ready for use.")

# 4. Generate description now that the file is ACTIVE
response = client.models.generate_content(
    model="gemini-2.5-flash", # Note: The model name was corrected from gemini-2.5-flash
    contents=[myfile, "Describe what is happening in this video."]
)

print(response.text)