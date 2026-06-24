import os
import resend

resend.api_key = os.getenv("RESEND_API_KEY")

def send_otp_email(to_email: str, otp: str, name: str = "there"):
    try:
        resend.Emails.send({
            "from": "Nudge <onboarding@resend.dev>",
            "to": to_email,
            "subject": "Your Nudge password reset code",
            "html": f"""
            <div style="font-family: Georgia, serif; max-width: 480px; margin: 0 auto; padding: 2rem; color: #111111;">
              <h2 style="font-weight: 400; margin-bottom: 1rem;">Hi {name},</h2>
              <p style="opacity: 0.65; margin-bottom: 1.5rem;">Here's your password reset code for Nudge:</p>
              <div style="background: #F5F1FF; border-radius: 12px; padding: 1.5rem; text-align: center; margin-bottom: 1.5rem;">
                <span style="font-size: 2rem; font-weight: 700; letter-spacing: 0.2em; color: #A78BFA;">{otp}</span>
              </div>
              <p style="opacity: 0.65; font-size: 0.88rem;">This code expires in 10 minutes. If you didn't request this, ignore this email.</p>
              <p style="opacity: 0.45; font-size: 0.78rem; margin-top: 2rem;">— Nudge by Addicoot</p>
            </div>
            """
        })
    except Exception as e:
        print(f"[resend] Email send failed: {e}")