TICKET_CATEGORY_RULES = """
Klassifiziere nach ITSM-Ticket-Typ und Hauptabsicht des Nutzers.
Ignoriere einzelne Schlüsselwörter, wenn sie nicht zur Hauptabsicht passen.

Ticket-Typen:

1. Complaint:
Wähle diesen Typ, wenn die Hauptabsicht eine Beschwerde, Unzufriedenheit,
Frust, Ärger oder Kritik an Support, Bearbeitung, Wartezeit, Kommunikation
oder fehlender Hilfe ist.
Das gilt auch dann, wenn zusätzlich ein technisches Problem erwähnt wird.
Typische Hinweise: "unhappy", "frustrated", "angry", "upset", "unacceptable",
"complained", "nobody fixed it", "no help in time", "not answered".

2. Problem:
Wähle diesen Typ nur, wenn die Hauptabsicht die Analyse einer wiederkehrenden
oder grundlegenden Ursache ist.
Ein aktueller Ausfall bleibt Incident, auch wenn mehrere Nutzer betroffen sind.
Problem ist passend bei Root-Cause-Analyse, wiederkehrenden Incidents,
bekannter Fehlerursache oder systematischer Untersuchung.

3. Change:
Wähle diesen Typ, wenn eine Änderung an System, Konfiguration, Berechtigung,
Rolle, Gruppe, Weiterleitung oder Prozess gewünscht wird.
Beispiele: neue Rolle vergeben, Gruppe anpassen, Zugriff ändern,
Mailbox-Weiterleitung ändern, Berechtigung erweitern.

4. Service Request:
Wähle diesen Typ bei Anfragen, Anträgen, Informationswünschen oder
administrativen Anliegen ohne Fokus auf eine technische Störung.
Wichtig: Zahlungs-, Gebühren-, Rechnungs-, Rückerstattungs- und
Accounting-Anliegen sind in diesem Projekt Service Request, auch wenn ein
Portal einen falschen Zahlungsstatus, eine Fehlermeldung oder ein Exportproblem zeigt.
Beispiele: Semesterbeitrag klären, Rechnung anfordern, Zahlungsstatus prüfen,
Rückerstattung, Software anfordern, Anleitung erhalten, Zugriff beantragen.

5. Incident:
Wähle diesen Typ, wenn ein IT-Service, System, Gerät, Netzwerk oder eine
Software aktuell nicht funktioniert und keine speziellere Kategorie oben passt.
Beispiele: Login unmöglich, WLAN aus, Drucker defekt, Moodle Upload geht nicht,
VPN verbindet nicht, Anwendung stürzt ab.

Priorität bei Überschneidungen:
Complaint > Problem > Change > Service Request > Incident.

Wenn ein Ticket sowohl eine technische Störung als auch ein Zahlungs-/Rechnungsanliegen enthält,
wähle Service Request, sofern Zahlung, Rechnung, Gebühr oder Accounting das eigentliche Ziel ist.

Wenn ein Ticket sowohl eine technische Störung als auch Ärger/Beschwerde enthält,
wähle Complaint, sofern die Beschwerde die Hauptabsicht ist.

Bewerte den Ticket-Typ immer anhand des GESAMTEN Chatverlaufs und aller bekannten Infos.
Gib genau einen Ticket-Typ zurück.
"""
