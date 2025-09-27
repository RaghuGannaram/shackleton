# import json
# import asyncio

# from typing import Dict, Any, List, Optional
# from urllib.parse import quote_plus

# from livekit.agents import function_tool, RunContext, ToolError

# import httpx

# import os
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
# from typing import Optional

# from configs.logger import get_logger

# log = get_logger()

# DEFAULT_TIMEOUT_MS = 10_000
# RETRY_ATTEMPTS = 1

# @function_tool()
# async def send_email(
#     context: RunContext,  # type: ignore
#     to_email: str,
#     subject: str,
#     message: str,
#     cc_email: Optional[str] = None
# ) -> str:
#     """
#     Send an email through Gmail.

#     Args:
#         to_email: Recipient email address
#         subject: Email subject line
#         message: Email body content
#         cc_email: Optional CC email address
#     """
#     try:
#         # Gmail SMTP configuration
#         smtp_server = "smtp.gmail.com"
#         smtp_port = 587

#         # Get credentials from environment variables
#         gmail_user = os.getenv("GMAIL_USER")
#         gmail_password = os.getenv("GMAIL_APP_PASSWORD")  # Use App Password, not regular password

#         if not gmail_user or not gmail_password:
#             log.error("Gmail credentials not found in environment variables")
#             return "Email sending failed: Gmail credentials not configured."

#         # Create message
#         msg = MIMEMultipart()
#         msg['From'] = gmail_user
#         msg['To'] = to_email
#         msg['Subject'] = subject

#         # Add CC if provided
#         recipients = [to_email]
#         if cc_email:
#             msg['Cc'] = cc_email
#             recipients.append(cc_email)

#         # Attach message body
#         msg.attach(MIMEText(message, 'plain'))

#         # Connect to Gmail SMTP server
#         server = smtplib.SMTP(smtp_server, smtp_port)
#         server.starttls()  # Enable TLS encryption
#         server.login(gmail_user, gmail_password)

#         # Send email
#         text = msg.as_string()
#         server.sendmail(gmail_user, recipients, text)
#         server.quit()

#         log.info(f"Email sent successfully to {to_email}")
#         return f"Email sent successfully to {to_email}"

#     except smtplib.SMTPAuthenticationError:
#         log.error("Gmail authentication failed")
#         return "Email sending failed: Authentication error. Please check your Gmail credentials."
#     except smtplib.SMTPException as e:
#         log.error(f"SMTP error occurred: {e}")
#         return f"Email sending failed: SMTP error - {str(e)}"
#     except Exception as e:
#         log.error(f"Error sending email: {e}")
#         return f"An error occurred while sending email: {str(e)}"
