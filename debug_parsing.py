from database import daf_to_float

def test_parsing(message):
    parts = [p.strip() for p in message.split(',')]
    print(f"Parts: {parts}")
    if len(parts) >= 9 and parts[0] == "הרשמה":
        try:
            name, last_name, city = parts[1], parts[2], parts[3]
            age = int(parts[4])
            tractate_name = parts[5]
            range_part = parts[6]
            print(f"Range part: '{range_part}'")
            if " עד " in range_part:
                start_str, end_str = range_part.split(" עד ")
                print(f"Start str: '{start_str}', End str: '{end_str}'")
                start_f, end_f = daf_to_float(start_str), daf_to_float(end_str)
            else:
                start_f = daf_to_float(range_part)
                end_f = start_f + 10.0
            
            rate, hour = float(parts[7]), int(parts[8])
            print(f"Success! Start: {start_f}, End: {end_f}, Rate: {rate}, Hour: {hour}")
        except Exception as e:
            print(f"Error parsing: {e}")
            import traceback
            traceback.print_exc()

message = 'הרשמה, משה, כהן, בני ברק, 25, ברכות, כב ע"א עד ל ע"א, 1.5, 18'
test_parsing(message)
