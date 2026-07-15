from dotenv import load_dotenv
import os
import requests
from requests.exceptions import ConnectionError, MissingSchema

from ..graph.models.TicketCategoryDecision import TICKET_CATEGORIES
from ..services.BackendLoggingService import BackendLogger

zammad_logger = BackendLogger("Zammad")

load_dotenv()

# The .env file format (server address and access token) is described in example.env.
server_address = os.getenv("ZAMMAD_INTERNAL_URL")
admin_access_token = os.getenv("ZAMMAD_API_TOKEN")
GENERAL_TIMEOUT = 5

# Authentication via token
headers = {"Authorization": f"Token token={admin_access_token}",
           "Content-Type": "application/json", }

# Display which user is currently authenticated
# response = requests.get(
#    url=f"{server_address}/api/v1/users/me",
#    headers = headers,
#    timeout=GENERAL_TIMEOUT
# )
# print(response.status_code)
# print(response.text)

# Map from our priority numbers to Zammad priority IDs
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
    Creates a ticket in the Zammad system via the REST API.
    See https://docs.zammad.org/en/latest/api/ticket/index.html#create

    :arg email: Customer email address
    :arg title: Ticket subject
    :arg body: Ticket body text
    :arg priority: Ticket priority, i.e. 0 = normal/non-urgent and 1 = high/urgent
    :arg group: Customer group (typically Users)
    :arg article_type: Article type (first message in the ticket,
        see https://docs.zammad.org/en/latest/api/ticket/articles.html#general-information-about-ticket-articles) (typically note)
    :arg internal: Defaults to False. If True, the ticket is only visible to helpdesk staff
    :arg state: Zammad ticket state, e.g. "new" or "closed"
    :arg kategorie: Value for the Zammad custom field "Kategorie" (custom select attribute)
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

        zammad_logger.info(f"Zammad ticket successfully created: {server_response.text}")
        return server_response.json().get("id")
    except ConnectionError:
        # Return the ticket id -1 if no connection could be built
        zammad_logger.error("Connection error: Could not reach Zammad to create ticket")
        return -1
    except MissingSchema:
        zammad_logger.error("Invalid URL for Zammad provided: Could not reach Zammad to create ticket")
        return -1
    except Exception as e:
        zammad_logger.error(f"Other error occured: {e}")
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
        zammad_logger.info(f"Category '{resolved_kategorie}' set on ticket {ticket_id}")
    except ConnectionError:
        zammad_logger.error("Connection error: Could not reach Zammad to update ticket kategorie")
    except MissingSchema:
        zammad_logger.error("Invalid URL for Zammad provided: Could not update ticket kategorie")
    except Exception as e:
        zammad_logger.error(f"Other error occured during kategorie update: {e}")

def update_ticket_title(ticket_id: int, title:str) -> None: 
    """ Overwrite the title of an existing Zammad ticket identifed by its ticket ID """ 
   
    if not title:
        return

    try:
        response = requests.put(
            url=f"{server_address}/api/v1/tickets/{ticket_id}",
            json={"title": title},
            headers=headers,
            timeout=GENERAL_TIMEOUT,
        )
        zammad_logger.info(f"Title '{title}' set on ticket {ticket_id}")
    except ConnectionError:
        zammad_logger.error("Connection error: Could not reach Zammad to update ticket title")
    except MissingSchema:
        zammad_logger.error("Invalid URL for Zammad provided: Could not update ticket title")
    except Exception as e:
        zammad_logger.error(f"Other error occured during title update: {e}")




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
    zammad_logger.info(f"Article added to ticket {ticket_id}")
    return response

def get_ticket_state(ticket_id: int) -> str:
    """
    Reads the current Zammad state of a ticket.

    :arg ticket_id: Ticket ID
    :return: State name (e.g. "new", "open", "closed") or "" on error
    """
    try:
        response = requests.get(
            url=f"{server_address}/api/v1/tickets/{ticket_id}",
            headers=headers,
            timeout=GENERAL_TIMEOUT,
        )
        if response.status_code != 200:
            zammad_logger.error(f"Could not read ticket {ticket_id}")
            return ""
        state_id = response.json().get("state_id")

        # Resolve state_id to state name
        state_response = requests.get(
            url=f"{server_address}/api/v1/ticket_states/{state_id}",
            headers=headers,
            timeout=GENERAL_TIMEOUT,
        )
        if state_response.status_code == 200:
            return state_response.json().get("name", "")
        return ""
    except ConnectionError:
        zammad_logger.error("Connection error: Could not reach Zammad to read ticket state")
        return ""
    except MissingSchema:
        zammad_logger.error("Invalid URL for Zammad provided: Could not read ticket state")
        return ""
    except Exception as e:
        zammad_logger.error(f"Other error occured while reading ticket state: {e}")
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
    Creates an automatically generated ticket (e.g. a problem ticket)
    via a fixed system sender and optionally tags it.

    :arg title: Ticket subject
    :arg body: Ticket body text
    :arg author_email: Email address of the system/sender account
    :arg priority: Priority (0 = normal, 1 = high/urgent)
    :arg tags: Optional list of tags
    :arg group: Zammad group
    :return: The new ticket ID or -1 on error
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
    """Adds a tag to a Zammad ticket."""
    try:
        response = requests.post(
            url=f"{server_address}/api/v1/tags/add",
            json={"object": "Ticket", "o_id": ticket_id, "item": tag},
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )
        zammad_logger.info(f"Tag '{tag}' added to ticket {ticket_id}")
    except ConnectionError:
        zammad_logger.error("Connection error: Could not reach Zammad to add tag to ticket")
    except MissingSchema:
        zammad_logger.error("Invalid URL for Zammad provided: Could not reach Zammad to add tag to ticket")
    except Exception as e:
        zammad_logger.error(f"Other error occured during tag addition: {e}")


def replace_tag_for_ticket(ticket_id: int, old_tag: str, new_tag: str):
    """Replaces a tag on a Zammad ticket."""
    try:

        response = requests.delete(
            url=f"{server_address}/api/v1/tags/remove",
            json={"object": "Ticket", "o_id": ticket_id, "item": old_tag},
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )
        zammad_logger.info(f"Tag '{old_tag}' removed from ticket {ticket_id}")

        response = requests.post(
            url=f"{server_address}/api/v1/tags/add",
            json={"object": "Ticket", "o_id": ticket_id, "item": new_tag},
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )
        zammad_logger.info(f"Tag '{new_tag}' added to ticket {ticket_id}")
    except ConnectionError:
        zammad_logger.error("Connection error: Could not reach Zammad to replace tag on ticket")
    except MissingSchema:
        zammad_logger.error("Invalid URL for Zammad provided: Could not reach Zammad to replace tag on ticket")
    except Exception as e:
        zammad_logger.error(f"Other error occured during tag replacement: {e}")

def log_ticket_close_event(ticket_id: int | None, source: str = "manual", metadata: dict | None = None):
    """
    Basic backend hook for ticket close events.

    The function only prints information for now, but it can be extended
    to trigger further backend logic later.
    """
    metadata = metadata or {}
    closure_source = "chatbot-API" if source in {"chatbot_api", "chatbot", "api"} else "ZIM-staff"

    log_entry_for_ticket_close_event = f"Zammad close event detected:\nTicket #{ticket_id} closed by: {closure_source}\n"



    if metadata.get("ticket_number"):
        log_entry_for_ticket_close_event += f"ticket_number: {metadata['ticket_number']}\n"
    if metadata.get("title"):
        log_entry_for_ticket_close_event += f"title: {metadata['title']}\n"
    if metadata.get("state"):
        log_entry_for_ticket_close_event += f"state: {metadata['state']}\n"

    zammad_logger.info(log_entry_for_ticket_close_event)

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

        zammad_logger.info(f"Ticket {ticket_id} marked as closed.")
    except ConnectionError:
        zammad_logger.error(f"Connection error: Could not reach Zammad to mark ticket {ticket_id} as closed")
    except MissingSchema:
        zammad_logger.error(f"Invalid URL for Zammad provided: Could not reach Zammad to mark ticket {ticket_id} as closed")
    except Exception as e:
        zammad_logger.error(f"Other error occured during marking ticket as closed: {e}")

def get_ticket_tags(ticket_id: int) -> list[str]:
    """
    Fetches the current tags of a Zammad ticket.
    :param ticket_id: The ticket id to look up.
    :return: List of tag names, empty list on failure.
    """
    try:
        response = requests.get(
            url=f"{server_address}/api/v1/tags",
            params={"object": "Ticket", "o_id": ticket_id},
            headers=headers,
            timeout=GENERAL_TIMEOUT
        )
        response.raise_for_status()
        return response.json().get("tags", [])
    except ConnectionError:
        zammad_logger.error(f"Connection error: Could not reach Zammad to fetch tags for ticket {ticket_id}")
        return []
    except MissingSchema:
        zammad_logger.error(f"Invalid URL for Zammad provided: Could not reach Zammad to fetch tags for ticket {ticket_id}")
        return []
    except Exception as e:
        zammad_logger.error(f"Other error occurred while fetching tags for ticket {ticket_id}: {e}")
        return []


def get_ticket_article_bodies(ticket_id: int | None, article_ids: list[int] | None = None) -> list[str]:
    """Fetch article bodies for a Zammad ticket using the API."""
    if not ticket_id:
        return []

    try:
        params = {"ticket_id": ticket_id}
        if article_ids:
            params["id[]"] = article_ids

        response = requests.get(
            url=f"{server_address}/api/v1/ticket_articles",
            params=params,
            headers=headers,
            timeout=GENERAL_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return [
                str(article.get("body", "")).strip()
                for article in payload
                if isinstance(article, dict) and str(article.get("body", "")).strip()
            ]
        return []
    except ConnectionError:
        zammad_logger.error(f"Connection error: Could not reach Zammad to fetch articles for ticket {ticket_id}")
        return []
    except MissingSchema:
        zammad_logger.error(f"Invalid URL for Zammad provided: Could not fetch ticket articles for {ticket_id}")
        return []
    except Exception as e:
        zammad_logger.error(f"Other error occurred while fetching ticket articles for {ticket_id}: {e}")
        return []
