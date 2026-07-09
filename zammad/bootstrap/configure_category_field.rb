# Configures the ticket attribute "Kategorie" for customer visibility in Zammad.
# The script is idempotent and can be executed on every container start.
#
# Category values are loaded from ticket_categories.json and must stay in sync with
# backend/graph/models/TicketCategoryDecision.py.

require "json"

categories_path = File.join(__dir__, "ticket_categories.json")
ticket_categories = JSON.parse(File.read(categories_path))

unless ticket_categories.is_a?(Array) && ticket_categories.all? { |entry| entry.is_a?(String) && !entry.strip.empty? }
  raise "ticket_categories.json must contain a non-empty array of category names"
end

category_options = ticket_categories.to_h { |category| [category, category] }

customer_create_screen = {
  shown: true,
  required: false,
  item_class: "column",
  nulloption: true,
}

agent_create_screen = {
  shown: true,
  required: false,
  item_class: "column",
  nulloption: true,
}

customer_edit_screen = {
  shown: true,
  required: false,
  nulloption: true,
}

agent_edit_screen = {
  shown: true,
  required: false,
  nulloption: true,
}

attribute_data = {
  object: "Ticket",
  name: "kategorie",
  display: "Kategorie",
  data_type: "select",
  data_option: {
    options: category_options,
    default: "",
    nulloption: true,
    null: true,
    multiple: false,
    translate: false,
    maxlength: 255,
  },
  active: true,
  screens: {
    create_middle: {
      "ticket.customer" => customer_create_screen,
      "ticket.agent" => agent_create_screen,
    },
    edit: {
      "ticket.customer" => customer_edit_screen,
      "ticket.agent" => agent_edit_screen,
    },
    view: {
      "ticket.customer" => { shown: true },
      "ticket.agent" => { shown: true },
    },
  },
  created_by_id: 1,
  updated_by_id: 1,
}

existing = ObjectManager::Attribute.find_by(
  object_lookup_id: ObjectLookup.by_name("Ticket"),
  name: "kategorie",
)

attribute_data[:force] = true if existing

ObjectManager::Attribute.add(attribute_data)

if ObjectManager::Attribute.migrations.any?
  ObjectManager::Attribute.migration_execute
  puts "Executed object manager migrations for ticket attribute 'Kategorie'."
end

puts "Configured ticket attribute 'Kategorie' (#{ticket_categories.size} categories) for customer visibility."
