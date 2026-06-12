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


## Troubleshooting

### Backend cannot reach Zammad during local end-to-end testing

During local end-to-end testing, the chatbot backend was unable to communicate with the Zammad instance although both applications were running.

The reason was that the backend container and the Zammad containers were attached to different Docker networks. Because of this network isolation, the backend could not resolve or reach the Zammad services.

To enable communication between both environments, the backend was temporarily connected to the external Docker network created by the Zammad stack:

```yaml
backend_app:
  networks:
    - default
    - zammad_default
```

The external network also had to be declared in the compose configuration:

```yaml
networks:
  zammad_default:
    external: true
```

Additionally, the `zammad_bootstrap` service was temporarily disabled during testing because it caused issues while rebuilding the local environment.

After applying these changes and rebuilding the containers, communication between the backend and Zammad was possible and end-to-end ticket creation could be tested successfully.

**Important:** These changes were introduced as a local development workaround. It is currently unclear whether this issue affects all development environments or only specific local Docker setups.


## AI Ticket Creation
To create a ticket, go to `localhost:8501`. After typing your mail address and your matriculation number, you can use the ZIM Helper to create a ticket by describing your concern.  
By typing in your credentials, our backend automatically creates a user account if you do not have one yet.  
After creating a ticket, you will get a mail from our Mailpit server, which you can observe on `localhost:8025`.

## Choose LLM Model (llama 3.2 3b vs. llama 3.3 70b (SAIA))
The backend supports seamless switching between our local model and the powerful SAIA model provided by the Academic Cloud. This is controlled via your local `.env` file (use the variables in the `example.env` as a reference).

* **`USE_SAIA_API=true`**: Activates the large, intelligent Llama-3.3-70B model via the SAIA API. (Requirement: A valid `SAIA_API_KEY` must be set in your `.env` file).
* **`USE_SAIA_API=false`** (or unset): Uses the local Ollama model as a fallback.
>  **IMPORTANT  RULE REGARDING THE API LIMIT!**
> We have a strict limit of **3,000 requests per month** for the SAIA API. To ensure we don't exhaust this quota in the middle of a sprint, please adhere to the following rule:
> * **Local Development & Debugging:** Always use Ollama (`USE_SAIA_API=false`) to verify that the code runs, pipelines are working, or the UI is loading.
> * **Quality Testing:** **Only** enable the SAIA API (`USE_SAIA_API=true`) when you specifically need to evaluate the quality of the AI responses or during a final feature review.