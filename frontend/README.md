
# Chatbot frontend

## How the chat interface is implemented
In the beginning the elements before the chat input are defined, such as the header. Also, there are form fields defined which must be filled out correctly. For the chat input a number of initial states are defined in the `initial_states` dictionary which then gets copied into the session state. 

The form fields are checked for validity in the `all_form_fields_valid` method which is called by the definition in the `user_input` to check whether to allow or block the user entering a chat message. If either the email or the immatriculation number are not valid, the input field for the chat is disabled.

The method `bot_starting_thinking` is called when the user presses the "Send" button in the chat input to send the chat message. This causes the input field to become disabled while the bot is generating the answer. This is to prevent the user from interrupting the bot while it generates the answer.

When the user sends a message, the user's input gets displayed in the chat history (`with st.chat_message("user"):`). Additionally, the bot shows first "Please wait... Answer is generated..." first, before the answer is generated. To generate the answer, the frontend sends a POST request to the chat endpoint in the backend along with the current chat's state. 

After the bot has replied, the answer is written into the visible chat history and the updated state that the backend returned is applied to the frontend, so that the next chat message can reuse the new state. Technically all the chat messages are Streamlit containers (`with st.chat_message("assistant"):` and then within the with statement one or more `st.write(...)`, as per https://docs.streamlit.io/develop/api-reference/chat/st.chat_message), so the chat messages can be extended to contain other elements as well.


## Starting the frontend
To test the frontend alone locally:
* run `python3 dev.py`
* open your browser at `http:localhost:5000`

Otherwise, the frontend runs on `http:localhost:5000` when the full project is started (using `docker compose`)
