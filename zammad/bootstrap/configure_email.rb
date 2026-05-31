# Configures the local development Zammad instance so agents can reply to tickets.
# The script is idempotent and can be executed on every container start.

# Umgebungsvariablen aus Docker in das Bootstrap-Skript ziehen
close_trigger_name = ENV.fetch("ZAMMAD_CLOSE_TRIGGER_NAME")
reopen_trigger_name = ENV.fetch("ZAMMAD_REOPEN_TRIGGER_NAME")
reopen_marker_tag = ENV.fetch("ZAMMAD_REOPEN_MARKER_TAG")
support_email = ENV.fetch("ZAMMAD_SUPPORT_EMAIL")
support_name = ENV.fetch("ZAMMAD_SUPPORT_NAME")
support_group = ENV.fetch("ZAMMAD_SUPPORT_GROUP")
smtp_host = ENV.fetch("ZAMMAD_SMTP_HOST")
smtp_port = ENV.fetch("ZAMMAD_SMTP_PORT")
environment = ENV.fetch("APP_ENV", "local")

# SMTP-Setup
smtp_options =
  if environment == "production"
    {
      "host" => smtp_host,
      "user" => ENV.fetch("ZAMMAD_SMTP_USER"),
      "password" => ENV.fetch("ZAMMAD_SMTP_PASSWORD"),
      "port" => smtp_port,
      "ssl_verify" => true,
      "domain" => ENV.fetch("ZAMMAD_SMTP_DOMAIN"),
      "enable_starttls_auto" => true
    }
  else
    {
      "host" => smtp_host,
      "user" => "",
      "password" => "",
      "port" => smtp_port,
      "ssl_verify" => false,
      "domain" => "localhost",
      "enable_starttls_auto" => false
    }
  end

# Zammad-Channel-Setup
channel = Channel.find_by(area: "Email::Notification", active: true) ||
          Channel.find_by(area: "Email::Notification")

raise "Zammad notification email channel was not initialized yet" unless channel

channel.update!(
  active: true,
  options: {
    "outbound" => {
      "adapter" => "smtp",
      "options" => smtp_options
    }
  },
  updated_by_id: 1
)

# Setup der E-Mail-Adresse, von der das Zammad-System
# die automatischen E-Mails schickt
address = EmailAddress.find_or_initialize_by(email: support_email)
address.assign_attributes(
  name: support_name,
  active: true,
  channel_id: channel.id,
  updated_by_id: 1
)
address.created_by_id ||= 1
address.save!

# Setup der Gruppe des Support-Systems
group = Group.find_by!(name: support_group)
group.update!(email_address_id: address.id, updated_by_id: 1)

# Setup der Statusmeldungen, wenn ein Ticket
# geschlossen oder wieder geöffnet wird
closed_state = Ticket::State.find_by!(name: "closed")
open_state = Ticket::State.find_by!(name: "open")
close_subject = 'Ihr Ticket wurde geschlossen (#{ticket.title})'
close_body = <<~'HTML'
  <div>Guten Tag,</div>
  <br/>
  <div>Ihr Ticket <b>(#{config.ticket_hook}#{ticket.number})</b> wurde geschlossen.</div>
  <br/>
  <div>Falls Sie weitere Fragen haben, antworten Sie einfach auf diese E-Mail.</div>
  <br/>
  <div>Ihr #{config.product_name} Team</div>
HTML
reopen_subject = 'Ihr Ticket wurde wieder geöffnet (#{ticket.title})'
reopen_body = <<~'HTML'
  <div>Guten Tag,</div>
  <br/>
  <div>Ihr Ticket <b>(#{config.ticket_hook}#{ticket.number})</b> wurde wieder geöffnet.</div>
  <br/>
  <div>Wir bearbeiten Ihr Anliegen weiter und melden uns bei Ihnen.</div>
  <br/>
  <div>Ihr #{config.product_name} Team</div>
HTML

# Setup der Trigger, wann welche Statusmeldung per E-Mail verschickt werden soll
close_trigger = Trigger.find_or_initialize_by(name: close_trigger_name)
close_trigger.assign_attributes(
  condition: {
    # Fire only while ticket is in closed state and not tagged as already notified.
    # "has changed" is too broad in Zammad and may match unrelated state transitions.
    "ticket.state_id" => {
      "operator" => "is",
      "value" => closed_state.id
    },
    "ticket.tags" => {
      "operator" => "contains all not",
      "value" => reopen_marker_tag
    }
  },
  perform: {
    "notification.email" => {
      "body" => close_body,
      "recipient" => "ticket_customer",
      "subject" => close_subject
    },
    "ticket.tags" => {
      "operator" => "add",
      "value" => reopen_marker_tag
    }
  },
  disable_notification: true,
  activator: "action",
  execution_condition_mode: "selective",
  active: true,
  updated_by_id: 1
)
close_trigger.created_by_id ||= 1
close_trigger.save!

reopen_trigger = Trigger.find_or_initialize_by(name: reopen_trigger_name)
reopen_trigger.assign_attributes(
  condition: {
    # Use "is open" here. In Zammad, "has changed" can match any state transition.
    "ticket.state_id" => {
      "operator" => "is",
      "value" => open_state.id
    },
    "ticket.tags" => {
      "operator" => "contains all",
      "value" => reopen_marker_tag
    }
  },
  perform: {
    "notification.email" => {
      "body" => reopen_body,
      "recipient" => "ticket_customer",
      "subject" => reopen_subject
    },
    "ticket.tags" => {
      "operator" => "remove",
      "value" => reopen_marker_tag
    }
  },
  disable_notification: true,
  activator: "action",
  execution_condition_mode: "selective",
  active: true,
  updated_by_id: 1
)
reopen_trigger.created_by_id ||= 1
reopen_trigger.save!

puts "Configured #{support_name} <#{support_email}> for group #{support_group} via #{smtp_host}:#{smtp_port}."
puts "Configured close notification trigger '#{close_trigger_name}'."
puts "Configured reopen notification trigger '#{reopen_trigger_name}'."
