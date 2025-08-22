#!/usr/bin/env python3
"""
Script para generar credenciales en formato de variables de entorno para Streamlit Cloud
"""

import bcrypt
import yaml
import json
from pathlib import Path

def generate_password_hash(password: str) -> str:
    """Generar hash de contraseña usando bcrypt"""
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    return password_hash.decode('utf-8')

def validate_password(password: str) -> bool:
    """Validar que la contraseña cumple requisitos de seguridad"""
    if len(password) < 8:
        print("❌ La contraseña debe tener al menos 8 caracteres")
        return False
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    if not all([has_upper, has_lower, has_digit, has_special]):
        print("❌ La contraseña debe contener:")
        print("   - Al menos una mayúscula")
        print("   - Al menos una minúscula")
        print("   - Al menos un número")
        print("   - Al menos un símbolo especial")
        return False
    
    return True

def generate_streamlit_secrets():
    """Generar credenciales para Streamlit Cloud"""
    print("🔐 Generador de Credenciales para Streamlit Cloud")
    print("=" * 50)
    
    # Solicitar información del usuario
    username = input("👤 Usuario: ").strip()
    if not username:
        print("❌ El usuario no puede estar vacío")
        return
    
    name = input("📝 Nombre completo: ").strip()
    if not name:
        print("❌ El nombre no puede estar vacío")
        return
    
    email = input("📧 Email: ").strip()
    if not email:
        print("❌ El email no puede estar vacío")
        return
    
    # Solicitar contraseña con validación
    while True:
        password = input("🔒 Contraseña: ")
        if validate_password(password):
            break
        print("🔄 Intenta de nuevo...")
    
    # Confirmar contraseña
    confirm_password = input("🔒 Confirmar contraseña: ")
    if password != confirm_password:
        print("❌ Las contraseñas no coinciden")
        return
    
    # Generar hash de contraseña
    password_hash = generate_password_hash(password)
    
    # Crear estructura de credenciales
    credentials = {
        "credentials": {
            "usernames": {
                username: {
                    "email": email,
                    "name": name,
                    "password": password_hash
                }
            }
        }
    }
    
    # Generar archivo de configuración local
    config_path = Path("config.yaml")
    if config_path.exists():
        response = input("⚠️  El archivo config.yaml ya existe. ¿Sobrescribir? (s/N): ")
        if response.lower() != 's':
            print("❌ Operación cancelada")
            return
    
    try:
        with open(config_path, 'w') as file:
            yaml.dump(credentials, file, default_flow_style=False, allow_unicode=True)
        print(f"✅ Archivo config.yaml creado/actualizado")
    except Exception as e:
        print(f"❌ Error al crear config.yaml: {e}")
        return
    
    # Generar formato para Streamlit Cloud
    print("\n" + "=" * 50)
    print("🌐 CONFIGURACIÓN PARA STREAMLIT CLOUD")
    print("=" * 50)
    print("Copia y pega esto en Streamlit Cloud > Advanced settings > Secrets:")
    print()
    
    # Formato JSON para st.secrets
    secrets_json = json.dumps(credentials, indent=2)
    print(secrets_json)
    
    print("\n" + "=" * 50)
    print("📋 INSTRUCCIONES PARA STREAMLIT CLOUD:")
    print("=" * 50)
    print("1. Ve a tu aplicación en Streamlit Cloud")
    print("2. Haz clic en 'Settings' (⚙️)")
    print("3. Ve a 'Secrets'")
    print("4. Pega el JSON de arriba en el campo de texto")
    print("5. Haz clic en 'Save'")
    print("6. Tu aplicación se reiniciará automáticamente")
    print()
    print("🔒 ¡Tus credenciales estarán seguras en la nube!")
    print("⚠️  IMPORTANTE: Nunca subas config.yaml a GitHub")

def main():
    """Función principal"""
    try:
        generate_streamlit_secrets()
    except KeyboardInterrupt:
        print("\n❌ Operación cancelada por el usuario")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    main()
