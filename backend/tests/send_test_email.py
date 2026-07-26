import smtplib
from email.message import EmailMessage


def send_test_email():
    """
        Sends a test email to local Mailpit (localhost:1025) to trigger the webhook
        and verify the automated Zammad ticket creation workflow.
    """
    msg = EmailMessage()

    # Header
    msg['Subject'] = "Dringend: eduroam funktioniert plötzlich nicht mehr"
    msg['From'] = "peter.krauza@stud.uni.de"
    msg['To'] = "it-support@uni.de"

    # Realistic email body
    email_body = """Hallo IT-Support-Team,

ich sitze gerade in der Bibliothek am Campus in Duisburg und versuche seit einer halben Stunde, mich mit dem WLAN zu verbinden. Das eduroam-Netzwerk wird zwar angezeigt, aber die Verbindung schlägt immer fehl ('Keine Verbindung mit diesem Netzwerk möglich'). 

Gestern Nachmittag hat genau hier am selben Platz noch alles problemlos funktioniert und ich habe an meinem Laptop (Windows 11) seitdem absolut nichts verändert oder geupdatet. 

Ich brauche das Internet heute wirklich dringend, weil wir uns gleich für unser ASEP-Masterprojekt online abstimmen müssen und ich auf Daten aus der Cloud zugreifen muss. Mein Smartphone ist komischerweise noch mit eduroam verbunden, nur der Laptop weigert sich komplett. 

Muss ich mein Profil irgendwie neu installieren oder ist das ein bekanntes Problem heute?

Danke für die schnelle Hilfe!

Viele Grüße
Peter Krauza
Studiengang: Informatik (M.Sc.)
"""

    msg.set_content(email_body)

    # Establish connection to Mailpit (localhost:1025) and send
    try:
        print("Sending test email to Mailpit...")
        with smtplib.SMTP('localhost', 1025) as server:
            server.send_message(msg)
        print("✅ Email sent successfully! Check the backend log to see if the webhook was triggered.")
    except ConnectionRefusedError:
        print("❌ Error: Could not connect to Mailpit. Is the Docker container running and is port 1025 exposed?")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")


if __name__ == "__main__":
    send_test_email()