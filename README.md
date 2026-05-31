# ai-ticket-management

## Endpoints

* Zammad Frontend:              http://localhost:8080
* Zammad API:                   http://localhost:8080/api/v1/
* Frontend App (Streamlit):     http://localhost:8501
* Backend API (FastAPI):        http://localhost:8000
* Mailpit UI:                   http://localhost:8025
* Mailpit SMTP:                 localhost:1025
* Flask (fake Shibboleth login) http://localhost:5000

## Run the Project

### Prerequisites
Before running the project, you need to create a .env file in the root directory. You can use the example.env as a template.  
Inside the template, you will se the `ZAMMAD_API_TOKEN` field, which you will fill out later.

### Start Zammad + Backend + Frontend
```bash
docker compose -f docker-compose.yml -f zammad/docker-compose.yml up -d

Older Docker Compose version:
docker-compose -f zammad\docker-compose.yml -f docker-compose.yml up -d
  ```
### Start Zammad + Backend + Frontend + Ollama
```bash
docker compose -f docker-compose.yml -f zammad/docker-compose.yml -f zammad/scenarios/add-ollama.yml up -d

Older Docker Compose version:
docker-compose -f docker-compose.yml -f zammad/docker-compose.yml -f zammad/scenarios/add-ollama.yml up -d
  ```

## Getting started

After the containers are set up, you can go on `localhost:8080` and register as an `admin` and create your Zammad Workspace.  
Then, you need to restart the container. Only then your Email SMTP server (here: Mailpit) can automatically connect to your Zammad Workspace.  

As said before, there is a `ZAMMAD_API_TOKEN` field in your .env. In order to generate a Token, go to `Profil/Token-Zugriff`.  
There you can generate a token. We highly recommend to enable "admin" and "ticket.agent".  
After copying the token, go to .env and paste it inside the `ZAMMAD_API_TOKEN` field, then restart your container.

GREAT! You are all set up and free to use Zammad.

## AI Ticket Creation
To create a ticket, go to `localhost:8501`. After typing your mail address and your matriculation number, you can use the ZIM Helper to create a ticket by describing your concern.  
By typing in your credentials, our backend automatically creates a user account if you do not have one yet.  
After creating a ticket, you will get a mail from our Mailpit server, which you can observe on `localhost:8025`.
