from tools.tool_actions import search_emails, send_email, delete_email

print(search_emails("invoice"))
print(send_email("manager@company.com", "Q3 Feedback", "Looks good, approved."))
print(delete_email("e001"))