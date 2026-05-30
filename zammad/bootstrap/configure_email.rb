close_trigger_name = ENV.fetch("ZAMMAD_CLOSE_TRIGGER_NAME")
reopen_trigger_name = ENV.fetch("ZAMMAD_REOPEN_TRIGGER_NAME")
reopen_marker_tag = ENV.fetch("ZAMMAD_REOPEN_MARKER_TAG")

# Erweiterungen Z.5-10 im Rahmen des Tests 
support_email = ENV.fetch("ZAMMAD_SUPPORT_EMAIL")
support_name = ENV.fetch("ZAMMAD_SUPPORT_NAME")
support_group = ENV.fetch("ZAMMAD_SUPPORT_GROUP")
smtp_host = ENV.fetch("ZAMMAD_SMTP_HOST")
smtp_port = ENV.fetch("ZAMMAD_SMTP_PORT")

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
