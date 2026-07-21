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

See [CONTRIBUTING.md](CONTRIBUTING.md) for the source-code language convention (English for code and technical docs; German for intentional user-facing product text).

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

## Choose LLM Model (qwen3:8b (Ollama) vs. openai-gpt-oss-120b (SAIA))
The backend supports seamless switching between our local model and the SAIA model provided by the Academic Cloud. This is controlled via your local `.env` file (use the variables in the `example.env` as a reference).

* **`USE_SAIA_API=true`**: Activates `openai-gpt-oss-120b` via the SAIA API. (Requirement: A valid `SAIA_API_KEY` must be set in your `.env` file).
* **`USE_SAIA_API=false`** (or unset): Uses the local Ollama model (`qwen3:8b`) as a fallback.
>  **IMPORTANT  RULE REGARDING THE API LIMIT!**
> We have a strict limit of **3,000 requests per month** for the SAIA API. To ensure we don't exhaust this quota in the middle of a sprint, please adhere to the following rule:
> * **Local Development & Debugging:** Always use Ollama (`USE_SAIA_API=false`) to verify that the code runs, pipelines are working, or the UI is loading.
> * **Quality Testing:** **Only** enable the SAIA API (`USE_SAIA_API=true`) when you specifically need to evaluate the quality of the AI responses or during a final feature review.

> **Planned direction:** the agreed target setup for whoever continues this project is the reverse of today's default — run `openai-gpt-oss-120b` locally (via Ollama) as the primary model, with a hosted API (e.g. Claude) only as a fallback when the local model is unavailable. This isn't implemented yet (see [docs/FUTURE_WORK.md](docs/FUTURE_WORK.md), "Local model → API fallback"); see [docs/LLM_HARDWARE_REQUIREMENTS.md](docs/LLM_HARDWARE_REQUIREMENTS.md) for the hardware this requires.

See the [docs/](docs) folder for further planning material: [FUTURE_WORK.md](docs/FUTURE_WORK.md) lists open work for future maintainers, and [LLM_HARDWARE_REQUIREMENTS.md](docs/LLM_HARDWARE_REQUIREMENTS.md) documents the LLM/hardware/model specifications for this project.


## Troubleshooting

Several issues occurred during development and testing of the Zammad integration. The following sections describe the causes and their corresponding solutions.

### Docker API Error

#### Problem

The following error message appeared when executing Docker commands:

```bash
request returned 500 Internal Server Error for API route ...
```

#### Cause

Docker Desktop was not running correctly or the Docker daemon was unavailable.

#### Solution

Restart Docker Desktop:

```bash
open -a Docker
```

Then verify that Docker is available again:

```bash
docker info
docker ps
```



### Backend Container Remains "unhealthy"

#### Problem

The backend container remained in the `unhealthy` state after startup.

#### Diagnosis

Check the container status:

```bash
docker ps | grep backend
```

View the logs:

```bash
docker logs ai-ticket-management-sprint2-backend_app-1 --tail=100
```

Check the health status:

```bash
docker inspect ai-ticket-management-sprint2-backend_app-1 --format='{{.State.Health.Status}}'
```

#### Cause

During the first startup, multiple embedding models are downloaded and loaded. This process may take several minutes and can temporarily cause the container to appear as `unhealthy` or `health: starting`.

#### Solution

Wait until the following messages appear:

```text
[retrieve] Ready.
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

Afterwards, the container should become `healthy`.




### Zammad API Token Errors

#### Problem

The following errors appeared during ticket creation:

```text
401 Can't find User for Token
```

or

```text
403 Token authorization failed
```

#### Cause

The Zammad API token was invalid, outdated, or not correctly loaded into the backend container.

#### Solution

Create a new API token in Zammad:

```text
Profile → Token Access
```

Add the token to the `.env` file:

```env
ZAMMAD_API_TOKEN=<TOKEN>
```




### Backend Still Uses the Old Token

#### Problem

Even after updating the token in the `.env` file, the backend container continued using the old token.

#### Diagnosis

Check the token in the `.env` file:

```bash
grep ZAMMAD_API_TOKEN .env
```

Check the token inside the container:

```bash
docker exec -it ai-ticket-management-sprint2-backend_app-1 printenv | grep ZAMMAD_API_TOKEN
```

#### Cause

A simple container restart does not always reload environment variable changes.

#### Solution

Recreate the backend container:

```bash
docker compose -f docker-compose.yml \
-f zammad/docker-compose.yml \
-f zammad/scenarios/add-ollama.yml \
up -d --force-recreate backend_app
```

Verify the token again:

```bash
docker exec -it ai-ticket-management-sprint2-backend_app-1 printenv | grep ZAMMAD_API_TOKEN
```



### Testing the Connection Between Backend and Zammad

After updating the token, the connection should be verified.

#### Test

```bash
docker exec -it ai-ticket-management-sprint2-backend_app-1 python -c 'import os,requests; r=requests.get(os.getenv("ZAMMAD_INTERNAL_URL")+"/api/v1/users/me", headers={"Authorization":"Token token="+os.getenv("ZAMMAD_API_TOKEN")}); print(r.status_code); print(r.text)'
```

#### Expected Result

```text
200
```

The command should also return the user information as JSON.

#### Result

After updating the token and recreating the container, the connection was established successfully and ticket creation worked again.



### Known Open Issue

#### Problem

When no matching solution can be found for a request, a ticket is not created automatically.

#### Observation

Instead, the chatbot enters a communication loop and repeatedly asks follow-up questions.

#### Possible Cause

The fallback flow for the "no solution found" scenario is not triggered correctly.


**Note:** The examples in this documentation use the project prefix `ai-ticket-management-sprint2`; if the repository is cloned into a directory with a different name, this prefix must be replaced accordingly in all Docker commands.
