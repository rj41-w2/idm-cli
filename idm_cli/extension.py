import os
import json
import shutil
import sys
import platform
import questionary
from idm_cli.utils import console, custom_style

def install_extension():
    src_ext_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'browser_extension'))
    base_dir = os.path.expanduser('~/.idm_cli')
    dest_ext_path = os.path.join(base_dir, 'browser_extension')
    
    is_updated = False
    try:
        os.makedirs(base_dir, exist_ok=True)
        if os.path.exists(dest_ext_path):
            old_manifest_path = os.path.join(dest_ext_path, 'manifest.json')
            new_manifest_path = os.path.join(src_ext_path, 'manifest.json')
            try:
                if os.path.exists(old_manifest_path) and os.path.exists(new_manifest_path):
                    with open(old_manifest_path, 'r') as f:
                        old_version = json.load(f).get("version", "")
                    with open(new_manifest_path, 'r') as f:
                        new_version = json.load(f).get("version", "")
                    if old_version and new_version and old_version != new_version:
                        is_updated = True
            except Exception:
                pass
            shutil.rmtree(dest_ext_path)
        shutil.copytree(src_ext_path, dest_ext_path)
    except Exception as e:
        console.print(f"[bold red]Failed to copy extension files:[/] {e}")
        return
        
    manifest_path = os.path.join(base_dir, 'com.idm.cli.json')
    existing_ext_id = None
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r') as f:
                old_manifest = json.load(f)
                origin = old_manifest.get("allowed_origins", [""])[0]
                if origin.startswith("chrome-extension://"):
                    existing_ext_id = origin.split("://")[1].strip("/")
        except Exception:
            pass
            
    console.print("\n[bold yellow]--- How to Install IDM-CLI Extension ---[/bold yellow]")
    console.print("[cyan]The browser extension allows you to download files and videos directly via IDM-CLI![/cyan]\n")
    console.print(f"Extension Folder: [bold green]{dest_ext_path}[/bold green]\n")
    console.print("1. Open Chrome or Edge and go to [bold]chrome://extensions[/bold] or [bold]edge://extensions[/bold]")
    console.print("2. Turn on [bold]'Developer mode'[/bold] (usually in the top right corner).")
    console.print("3. Click [bold]'Load unpacked'[/bold] and select the Extension Folder shown above.")
    console.print("4. Copy the Extension ID that is generated.\n")
    
    if existing_ext_id:
        console.print(f"[bold cyan]You have already configured this Extension ID: {existing_ext_id}[/bold cyan]")
        if is_updated:
            console.print("[bold yellow]Update Note:[/bold yellow] The extension files on your disk have been updated to the latest version.")
            console.print("To apply the update in your browser, go to [bold]chrome://extensions[/bold] and click the [bold]'Reload'[/bold] icon (↻) on the IDM-CLI extension card.\n")
        prompt_text = "If you want to change the ID, paste the new ID here, otherwise just press enter:"
    else:
        prompt_text = "Paste the Extension ID here (or press enter):"
        
    ext_id = questionary.text(prompt_text, style=custom_style).ask()
    if not ext_id:
        if existing_ext_id:
            console.print("[bold green]Keeping existing extension ID.[/bold green]\n")
        else:
            console.print("[bold red]Installation Cancelled.[/bold red]\n")
        return
        
    ext_id = ext_id.strip()
    
    system_name = platform.system()
    
    if system_name == "Windows":
        import winreg
        bat_path = os.path.join(base_dir, 'native_host.bat')
        with open(bat_path, 'w') as f:
            f.write(f"@echo off\n{sys.executable} -m idm_cli.native_host\n")
            
        manifest_path = os.path.join(base_dir, 'com.idm.cli.json')
        manifest = {
            "name": "com.idm.cli",
            "description": "IDM-CLI Native Messaging Host",
            "path": bat_path,
            "type": "stdio",
            "allowed_origins": [
                f"chrome-extension://{ext_id}/"
            ]
        }
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=4)
            
        try:
            key_path = r"Software\Google\Chrome\NativeMessagingHosts\com.idm.cli"
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_path)
            winreg.CloseKey(key)
            
            edge_key_path = r"Software\Microsoft\Edge\NativeMessagingHosts\com.idm.cli"
            edge_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, edge_key_path)
            winreg.SetValueEx(edge_key, "", 0, winreg.REG_SZ, manifest_path)
            winreg.CloseKey(edge_key)
            
            console.print("\n[bold green]Success! The extension is now connected to IDM-CLI![/bold green]")
            console.print("[dim]You can now catch any link through the extension![/dim]\n")
        except Exception as e:
            console.print(f"\n[bold red]Failed to write to registry:[/] {e}\n")
    else:
        sh_path = os.path.join(base_dir, 'native_host.sh')
        with open(sh_path, 'w') as f:
            f.write(f"#!/bin/bash\n{sys.executable} -m idm_cli.native_host\n")
        os.chmod(sh_path, 0o755)

        manifest_path = os.path.join(base_dir, 'com.idm.cli.json')
        manifest = {
            "name": "com.idm.cli",
            "description": "IDM-CLI Native Messaging Host",
            "path": sh_path,
            "type": "stdio",
            "allowed_origins": [
                f"chrome-extension://{ext_id}/"
            ]
        }
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=4)

        target_dirs = [
            os.path.expanduser("~/.config/google-chrome/NativeMessagingHosts"),
            os.path.expanduser("~/.config/chromium/NativeMessagingHosts"),
            os.path.expanduser("~/.config/microsoft-edge/NativeMessagingHosts"),
            os.path.expanduser("~/Library/Application Support/Google/Chrome/NativeMessagingHosts"),
            os.path.expanduser("~/Library/Application Support/Chromium/NativeMessagingHosts"),
            os.path.expanduser("~/Library/Application Support/Microsoft Edge/NativeMessagingHosts")
        ]

        success_count = 0
        for d in target_dirs:
            if os.path.exists(os.path.dirname(d)):
                os.makedirs(d, exist_ok=True)
                dest_manifest = os.path.join(d, 'com.idm.cli.json')
                try:
                    shutil.copy(manifest_path, dest_manifest)
                    success_count += 1
                except Exception:
                    pass

        if success_count > 0:
            console.print("\n[bold green]Success! The extension is now connected to IDM-CLI![/bold green]")
            console.print("[dim]You can now catch any link through the extension![/dim]\n")
        else:
            console.print("\n[bold yellow]Could not find standard browser directories to copy the manifest. Please configure manually.[/bold yellow]\n")

