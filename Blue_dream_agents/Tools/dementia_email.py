import base64
import os
import pickle
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GmailAgent:
    """Gmail sender used by the fall-alert path."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    def __init__(self, credentials_file="credentials.json", token_file="token.pickle"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.credentials_file = os.path.join(script_dir, credentials_file)
        self.token_file = os.path.join(script_dir, token_file)
        self.service = self.authenticate()

    def authenticate(self):
        """Authenticate and return a Gmail service object."""

        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file,
                    self.SCOPES,
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_file, "wb") as token:
                pickle.dump(creds, token)

        return build("gmail", "v1", credentials=creds)

    def send_alert_email(
        self,
        to: str,
        subject: str,
        alert_type: str,
        location: str,
        timestamp: str,
        image_path: Optional[str] = None,
    ) -> Dict:
        """Send a styled fall-alert email with an optional inline screenshot."""

        image_section = ""
        if image_path and os.path.exists(image_path):
            image_section = """
                <div style="margin-top: 20px; text-align: center;">
                    <p style="font-weight: bold; margin-bottom: 10px;">
                        Captured Screenshot:
                    </p>
                    <img
                        src="cid:fall_screenshot"
                        style="max-width: 100%; border-radius: 8px; border: 2px solid #d32f2f;"
                        alt="Fall Detection Screenshot"
                    />
                </div>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    margin: 0;
                    padding: 0;
                    background-color: #f4f4f4;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    background: #fff;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }}
                .header {{
                    background-color: #d32f2f;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    text-transform: uppercase;
                    letter-spacing: 2px;
                }}
                .content {{
                    padding: 30px;
                }}
                .alert-box {{
                    background-color: #ffebee;
                    border-left: 5px solid #d32f2f;
                    padding: 15px;
                    margin-bottom: 25px;
                }}
                .alert-title {{
                    color: #d32f2f;
                    font-weight: bold;
                    font-size: 18px;
                    margin-bottom: 5px;
                    display: block;
                }}
                .info-row {{
                    margin-bottom: 10px;
                    border-bottom: 1px solid #eee;
                    padding-bottom: 10px;
                }}
                .label {{
                    font-weight: bold;
                    color: #555;
                    width: 100px;
                    display: inline-block;
                }}
                .value {{
                    color: #000;
                    font-weight: 500;
                }}
                .footer {{
                    background-color: #eee;
                    padding: 15px;
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Emergency Alert</h1>
                </div>
                <div class="content">
                    <div class="alert-box">
                        <span class="alert-title">{alert_type}</span>
                        A critical event has been detected by the Blue Dream monitoring system.
                    </div>
                    <div class="info-row">
                        <span class="label">Location:</span>
                        <span class="value">{location}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Time:</span>
                        <span class="value">{timestamp}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Status:</span>
                        <span class="value" style="color: #d32f2f; font-weight: bold;">
                            Immediate Attention Required
                        </span>
                    </div>
                    <p>Please check on the individual immediately.</p>
                    {image_section}
                </div>
                <div class="footer">
                    Blue Dream Monitoring System &bull; Automated Alert<br />
                    Please do not reply to this email.
                </div>
            </div>
        </body>
        </html>
        """

        try:
            message = MIMEMultipart("related")
            message["To"] = to
            message["Subject"] = subject
            message.attach(MIMEText(html_content, "html"))

            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as image_file:
                        image_data = image_file.read()

                    extension = os.path.splitext(image_path)[1].lower()
                    subtype = "jpeg" if extension in {".jpg", ".jpeg"} else "png"
                    image = MIMEImage(image_data, _subtype=subtype)
                    image.add_header("Content-ID", "<fall_screenshot>")
                    image.add_header(
                        "Content-Disposition",
                        "inline",
                        filename=os.path.basename(image_path),
                    )
                    message.attach(image)
                except Exception as exc:
                    print(f"Warning: Could not embed fall screenshot: {exc}")

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            sent_message = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )
            print(f"Alert email sent successfully! Message ID: {sent_message['id']}")
            return {"success": True, "message_id": sent_message["id"]}
        except HttpError as exc:
            print(f"An error occurred sending alert email: {exc}")
            return {"success": False, "error": str(exc)}
