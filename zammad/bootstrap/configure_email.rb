# Configures the local development Zammad instance so agents can reply to tickets.
# The script is idempotent and can be executed on every container start.

support_email = ENV.fetch("ZAMMAD_SUPPORT_EMAIL")
support_name = ENV.fetch("ZAMMAD_SUPPORT_NAME")
support_group = ENV.fetch("ZAMMAD_SUPPORT_GROUP")
smtp_host = ENV.fetch("ZAMMAD_SMTP_HOST")
smtp_port = ENV.fetch("ZAMMAD_SMTP_PORT")
environment = ENV.fetch("APP_ENV", "local")

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

address = EmailAddress.find_or_initialize_by(email: support_email)
address.assign_attributes(
  name: support_name,
  active: true,
  channel_id: channel.id,
  updated_by_id: 1
)
address.created_by_id ||= 1
address.save!

group = Group.find_by!(name: support_group)
group.update!(email_address_id: address.id, updated_by_id: 1)