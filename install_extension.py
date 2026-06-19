import os
import json
import winreg

def main():
    ext_id = input("Enter your Extension ID: ").strip()
    if not ext_id:
        print("Extension ID cannot be empty.")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    bat_path = os.path.join(script_dir, "native_host.bat")
    json_path = os.path.join(script_dir, "com.idm.cli.json")

    manifest = {
        "name": "com.idm.cli",
        "description": "IDM CLI Native Host",
        "path": bat_path,
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{ext_id}/"
        ]
    }

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=4)
    print(f"Created {json_path}")

    # Write to Registry
    reg_path = r"Software\Google\Chrome\NativeMessagingHosts\com.idm.cli"
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, json_path)
        winreg.CloseKey(key)
        print(f"Successfully added registry key: HKEY_CURRENT_USER\\{reg_path}")
    except Exception as e:
        print(f"Error writing to registry: {e}")

if __name__ == '__main__':
    main()
