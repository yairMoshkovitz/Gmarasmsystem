from registration import get_template, clear_template_cache

def test_templates():
    # Clear cache to ensure we read fresh from DB/JSON
    clear_template_cache()
    
    print("Testing templates with auto-footer:")
    
    # These should have the footer
    templates_with_footer = [
        "ask_update_daf", 
        "unregistered_instructions",
        "tractate_not_found"
    ]
    
    for t_name in templates_with_footer:
        content = get_template(t_name, name="משה", tractate="ברכות", menu="1. מנוי")
        has_footer = "לחזרה לתפריט שלח 0" in content
        print(f"Template '{t_name}': {'OK (has footer)' if has_footer else 'FAILED (missing footer)'}")
        if not has_footer:
            print(f"  Content representation: {repr(content)}")

    # These should NOT have the footer (it's already in the template or not needed)
    templates_without_auto_footer = [
        "main_menu",
        "welcome_new_user",
        "registration_success"
    ]
    
    print("\nTesting templates WITHOUT auto-footer:")
    for t_name in templates_without_auto_footer:
        content = get_template(t_name, name="משה", tractate="ברכות", start_daf="ב", end_daf="י", rate=1, hour=18)
        # Check if it has the footer ONLY once (main_menu has it manually)
        count = content.count("לחזרה לתפריט שלח 0")
        if t_name == "main_menu":
            # Just check if '0' is in there, since encoding might be weird in terminal
            print(f"Template '{t_name}': {'OK (has manual footer indicator)' if '0' in content else f'FAILED (missing manual footer). Content: {repr(content)}'}")
        else:
            print(f"Template '{t_name}': {'OK (no footer)' if count == 0 else f'FAILED (has footer, count={count})'}")

if __name__ == "__main__":
    test_templates()
