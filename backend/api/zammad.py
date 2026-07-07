from dotenv import load_dotenv
import os
import requests
from requests.exceptions import ConnectionError, MissingSchema

from ..graph.models.TicketCategoryDecision import TICKET_CATEGORIES

load_dotenv()

# Format der .env-Datei, woraus die Server-Adresse und der Zugangstoken
# gelesen werden ist in example.env beschrieben.
server_address = os.getenv("ZAMMAD_INTERNAL_URL")
admin_access_token = os.getenv("ZAMMAD_API_TOKEN")
GENERAL_TIMEOUT = 5

# Anmeldung über Token
headers = {"Authorization": f"Token token={admin_access_token}",
           "Content-Type": "application/json", }

# Anzeigen als welcher Benutzer ich aktuell angemeldet bin
# response = requests.get(
#    url=f"{server_address}/api/v1/users/me",
#    headers = headers,
#    timeout=GENERAL_TIMEOUT
# )
# print(response.status_code)
# print(response.text)

# Map von unseren Priority-Nummern zu den Zammad-Priority-Nummern
priority_number_to_zammad_priority_id_map = {
    0: 2,  # normal / non-urgent
    1: 3  # high / urgent
}

def resolve_zammad_kategorie(category: str | None) -> str | None:
    """Return a category value that is valid for the Zammad select field."""
    value = (category or "").strip()
    if value in TICKET_CATEGORIES:
        return value
    return None


def create_ticket_by_user_email(
        email: str,
        title: str,
        body: str,
        priority: int = 0,
        group: str = "Users",
        article_type: str = "web",
        internal: bool = False,
        state: str = "new",
        kategorie: str | None = None,
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
    :arg state: Zammad-Status des Tickets, z.B. "new" oder "closed"
    :arg kategorie: Wert für das Zammad-Feld "Kategorie" (custom select attribute)
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
        "state": state,
    }

    resolved_kategorie = resolve_zammad_kategorie(kategorie)
    if resolved_kategorie:
        json_body_for_ticket["kategorie"] = resolved_kategorie

    try:
        server_response = requests.post(url=f"{server_address}/api/v1/tickets",
                                        json=json_body_for_ticket,
                                        headers=headers,
                                        timeout=GENERAL_TIMEOUT)

        print(server_response.status_code)
        print(server_response.text)
        return server_response.json().get("id")
    except ConnectionError:
        # Return the ticket id -1 if no connection could be built
        print(f"Connection error: Could not reach Zammad to create ticket")
        return -1
    except MissingSchema:
        print(f"Invalid URL for Zammad provided: Could not reach Zammad to create ticket")
        return -1
    except Exception as e:
        print(f"Other error occured: {e}")
        return -1


def update_ticket_kategorie(ticket_id: int, kategorie: str | None) -> None:
    """Set the Zammad custom field 'kategorie' on an existing ticket."""
    resolved_kategorie = resolve_zammad_kategorie(kategorie)
    if not resolved_kategorie:
        return

    try:
        response = requests.put(
            url=f"{server_address}/api/v1/tickets/{ticket_id}",
            json={"kategorie": resolved_kategorie},
            headers=headers,
            timeout=GENERAL_TIMEOUT,
        )
        print(
            f"Kategorie '{resolved_kategorie}' set on ticket {ticket_id}: "
            f"{response.status_code}"
        )
    except ConnectionError:
        print("Connection error: Could not reach Zammad to update ticket kategorie")
    except MissingSchema:
        print("Invalid URL for Zammad provided: Could not update ticket kategorie")
    except Exception as e:
        print(f"Other error occured during kategorie update: {e}")


def add_article_to_ticket(ticket_id: int, body: str, sender: str = "Agent",
                           article_type: str = "note", internal: bool = True):
    """
    Append an article to an existing Zammad ticket.
    sender: "Agent" for AI reply,
            "Customer" for customer messages.
    """
    response = requests.post(
        url=f"{server_address}/api/v1/ticket_articles",
        json={
            "ticket_id": ticket_id,
            "body": body,
            "type": article_type,
            "internal": internal,
            "sender": sender,
        },
        headers=headers,
        timeout=GENERAL_TIMEOUT
    )
    print(f"Article added to ticket {ticket_id}: {response.status_code}")
    return response

def get_ticket_state(ticket_id: int) -> str:
    """
    Liest den aktuellen Zammad-Status eines Tickets aus.

    :arg ticket_id: ID des Tickets
    :return: Statusname (z. B. "new", "open", "closed") oder "" bei Fehler
    """
    try:
        response = requests.get(
            url=f"{server_address}/api/v1/tickets/{ticket_id}",
            headers=headers,
            timeout=GENERAL_TIMEOUT,
        )
        if response.status_code != 200:
            print(f"Could not read ticket {ticket_id}: {response.status_code}")
            return ""
        state_id = response.json().get("state_id")

        # state_id -> state name auflösen
        state_response = requests.get(
            url=f"{server_address}/api/v1/ticket_states/{state_id}",
            headers=headers,
            timeout=GENERAL_TIMEOUT,
        )
        if state_response.status_code == 200:
            return state_response.json().get("name", "")
        return ""
    except ConnectionError:
        print("Connection error: Could not reach Zammad to read ticket state")
        return ""
    except MissingSchema:
        print("Invalid URL for Zammad provided: Could not read ticket state")
        return ""
    except Exception as e:
        print(f"Other error occured while reading ticket state: {e}")
        return ""


def create_system_ticket(
        title: str,
        body: str,
        author_email: str,
        priority: int = 1,
        tags: list[str] | None = None,
        group: str = "Users",
):
    """
    Erstellt ein automatisch generiertes Ticket (z. B. ein Problem-Ticket)
    über einen festen System-Absender und versieht es optional mit Tags.

    :arg title: Betreff des Tickets
    :arg body: Text im Ticket
    :arg author_email: E-Mail-Adresse des System-/Absender-Kontos
    :arg priority: Priorität (0 = normal, 1 = high/urgent)
    :arg tags: Optionale Liste von Tags
    :arg group: Zammad-Gruppe
    :return: Die neue Ticket-ID oder -1 bei Fehler
    """
    ticket_id = create_ticket_by_user_email(
        email=author_email,
        title=title,
        body=body,
        priority=priority,
        group=group,
        article_type="note",
        internal=True,
        state="new",
    )

    if ticket_id and ticket_id != -1 and tags:
        for tag in tags:
            add_tag_to_ticket(ticket_id, tag)

    return ticket_id


def add_tag_to_ticket(ticket_id: int, tag: str):
    """Fügt einen Tag zu einem Zammad-Ticket hinzu."""
    try:
        response = requests.post(
            url=f"{server_address}/api/v1/tags/add",
            json={"object": "Ticket", "o_id": ticket_id, "item": tag},
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )
        print(f"Tag '{tag}' added to ticket {ticket_id}: {response.status_code}")
    except ConnectionError:
        print(f"Connection error: Could not reach Zammad to add tag to ticket")
    except MissingSchema:
        print(f"Invalid URL for Zammad provided: Could not reach Zammad to add tag to ticket")
    except Exception as e:
        print(f"Other error occured during tag addition: {e}")


def replace_tag_for_ticket(ticket_id: int, old_tag: str, new_tag: str):
    """Ersetzt einen Tag eines Zammad-Tickets."""
    try:

        response = requests.delete(
            url=f"{server_address}/api/v1/tags/remove",
            json={"object": "Ticket", "o_id": ticket_id, "item": old_tag},
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )
        print(f"Tag '{old_tag}' removed from ticket {ticket_id}: {response.status_code}")

        response = requests.post(
            url=f"{server_address}/api/v1/tags/add",
            json={"object": "Ticket", "o_id": ticket_id, "item": new_tag},
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )
        print(f"Tag '{new_tag}' added to ticket {ticket_id}: {response.status_code}")
    except ConnectionError:
        print(f"Connection error: Could not reach Zammad to replace tag on ticket")
    except MissingSchema:
        print(f"Invalid URL for Zammad provided: Could not reach Zammad to replace tag on ticket")
    except Exception as e:
        print(f"Other error occured during tag replacement: {e}")

def mark_ticket_as_closed(ticket_id:int):
    """
    Sends a Zammad API call to close the ticket (state is set to closed) with the provided ticket ID.
    :param ticket_id: The ticket id of the ticket to close
    """
    try:
        response = requests.put(
            url=f"{server_address}/api/v1/tickets/{ticket_id}",
            json={
                "state":"closed",
            },
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )

        print(f"Ticket {ticket_id} marked as closed.")
    except ConnectionError:
        print(f"Connection error: Could not reach Zammad to add mark ticket as closed")
    except MissingSchema:
        print(f"Invalid URL for Zammad provided: Could not reach Zammad to mark ticket as closed")
    except Exception as e:
        print(f"Other error occured during marking ticket as closed: {e}")
