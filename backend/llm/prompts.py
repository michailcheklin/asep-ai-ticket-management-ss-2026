
TICKET_CATEGORY_RULES = """
Klassifiziere nach Hauptabsicht des Nutzers, nicht nach einzelnen Schlüsselwörtern.

Kategorien:

1. Beschwerde:
Wähle diese Kategorie nur, wenn die Hauptabsicht des Nutzers eine Beschwerde über Support,
Bearbeitung, Wartezeit oder schlechte Kommunikation ist.
Ein technisches Problem allein ist keine Beschwerde.

2. Rechnung:
Wähle diese Kategorie, wenn das Hauptproblem Zahlung, Gebühren, Rechnung, Rückerstattung
oder Zahlungsstatus betrifft.
Auch technische Fehler in einem Zahlungsportal bleiben Rechnung, wenn die Zahlung das
eigentliche Ziel ist.

3. Zugang/Login:
Wähle diese Kategorie, wenn der Nutzer keinen Zugang zu einem Konto oder Uni-System bekommt.
Dazu gehören Login-Probleme, Passwort, 2FA, gesperrte Accounts, falsche Zugangsdaten oder
Authentifizierung — auch ohne explizite Nennung von Systemnamen.

4. Technisches Problem:
Wähle diese Kategorie, wenn ein System, Gerät, Netzwerk oder eine Software technisch nicht
funktioniert, aber der Schwerpunkt nicht auf Login, Zahlung oder Beschwerde liegt.

5. Allgemeine Anfrage:
Wähle diese Kategorie, wenn der Nutzer nur Informationen möchte oder noch kein konkretes
Problem beschreibt.

Bei Überschneidungen gilt:
Beschwerde > Rechnung > Zugang/Login > Technisches Problem > Allgemeine Anfrage.

Bewerte die Kategorie immer anhand des GESAMTEN Chatverlaufs und aller bekannten Infos.
Gib genau eine Kategorie zurück.
"""

# Damit der Chabot menschlicher wirkt:
# Wird den System-Prompts vorangestellt, damit Tonfall und Anrede ueberall
# einheitlich sind (durchgaengig Du, freundlich, konkret, ehrlich bei Unwissen).
BOT_PERSONA = (
    "Du bist der ZIM Helper, der IT-Support-Bot des Zentrums fuer Information und "
    "Medientechnik (ZIM) einer Universitaet. "
    "WICHTIG: Sprich den Nutzer AUSNAHMSLOS mit 'du' an, niemals mit 'Sie' oder 'Ihnen' — "
    "auch nicht in Anleitungen oder foermlichen Passagen."
    "Du bist freundlich, konkret und fasst dich kurz. Wenn du etwas nicht weisst, sagst du "
    "das ehrlich, statt zu raten."
)

