import smtplib
from email.message import EmailMessage


def send_test_email():
    # E-Mail-Objekt erstellen
    msg = EmailMessage()

    # Header definieren
    msg['Subject'] = "Dringend: eduroam funktioniert plötzlich nicht mehr"
    msg['From'] = "peter.krauza@stud.uni.de"
    msg['To'] = "it-support@uni.de"

    # Realistischer E-Mail-Body
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

    # Verbindung zu Mailpit (localhost:1025) aufbauen und senden
    try:
        print("Sende Test-E-Mail an Mailpit...")
        with smtplib.SMTP('localhost', 1025) as server:
            server.send_message(msg)
        print("✅ E-Mail erfolgreich gesendet! Schau im Backend-Log nach, ob der Webhook ausgelöst wurde.")
    except ConnectionRefusedError:
        print("❌ Fehler: Konnte nicht zu Mailpit verbinden. Läuft der Docker-Container und ist Port 1025 freigegeben?")
    except Exception as e:
        print(f"❌ Ein unerwarteter Fehler ist aufgetreten: {e}")


if __name__ == "__main__":
    send_test_email()