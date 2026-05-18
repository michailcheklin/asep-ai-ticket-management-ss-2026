Official Documentation: https://docs.zammad.org/en/latest/install/docker-compose.html

# Start Zammad

To start Zammad with default settings, you need to run the following commands:

```bash
$ cd zammad
```

```bash
$ docker compose up -d
```

After the stack is ready, you can access Zammad via the configured Docker host and port, e.g. http://localhost:8080/.

Instead of the command before, you can use the following to start Zammad with Ollama inside a container:
```bash
docker compose -f docker-compose.yml -f scenarios/add-ollama.yml up -d
```
