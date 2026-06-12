from dotenv import load_dotenv
import os
import requests
load_dotenv()

# Format der .env-Datei, woraus die Server-Adresse und der Zugangstoken
# gelesen werden ist in example.env beschrieben.
server_address = os.getenv("ZAMMAD_INTERNAL_URL")
admin_access_token = os.getenv("ZAMMAD_API_TOKEN")
GENERAL_TIMEOUT = 5

# Anmeldung über Token
headers = {"Authorization": f"Token token={admin_access_token}",
           "Content-Type": "application/json",}

# Anzeigen als welcher Benutzer ich aktuell angemeldet bin
#response = requests.get(
#    url=f"{server_address}/api/v1/users/me",
#    headers = headers,
#    timeout=GENERAL_TIMEOUT
#)
#print(response.status_code)
#print(response.text)

# Map von unseren Priority-Nummern zu den Zammad-Priority-Nummern
priority_number_to_zammad_priority_id_map = {
    0:2, # normal / non-urgent
    1:3  # high / urgent
}


def create_ticket_by_user_email(
        email:str,
        title:str,
        body:str,
        priority:int=0,
        group:str = "Users",
        article_type:str = "web",
        internal:bool = False
):
    """
    Erstellt ein Ticket im Zammad-System über die REST-API,
    s. https://docs.zammad.org/en/latest/api/ticket/index.html#create
    mittels der E-Mail-Adresse des Kunden, sowie dem Titel und Inhalt

    :arg email: E-Mail-Adresse des Kunden
    :arg title: Betreff des Tickets
    :arg body: Text im Ticket
    :arg priority: Die Priorität des Tickets, d. h. 0 = normal/non-urgent und 1 = high/urgent
    :arg group: Gruppe des Kunden (i. d. R. Users)
    :arg article_type: Typ des Artikels (erste Nachricht im Ticket,
        s. https://docs.zammad.org/en/latest/api/ticket/articles.html#general-information-about-ticket-articles) (i. d. R. note)
    :arg internal: Standardmäßig False. Falls True, ist das Ticket nur für die Mitarbeitenden des Helpdesks sichtbar
    """
    json_body_for_ticket = {
        "title": f"{title}",
        "group": f"{group}",
        "customer_id": f"guess:{email}",
        "article": {
            "body": f"{body}",
            "type": f"{article_type}",
            "internal": internal,
            "sender": "Customer",
        },
        "priority_id": priority_number_to_zammad_priority_id_map[priority],
    }

    server_response = requests.post(url=f"{server_address}/api/v1/tickets",
                                    json=json_body_for_ticket,
                                    headers=headers,
                                    timeout=GENERAL_TIMEOUT)

    print(server_response.status_code)
    print(server_response.text)



# create_ticket_by_user_email(email="example@example.com", title="Help request", body="Hello, I need help!",)
