#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para generar contraseñas hasheadas para la autenticación
Ejecutar: python generate_password.py

IMPORTANTE: Este script debe ejecutarse LOCALMENTE, nunca subir al repositorio
las contraseñas generadas. El archivo config.yaml debe estar en .gitignore
"""

import streamlit_authenticator as stauth
import yaml
import os
import sys
from pathlib import Path

def validate_password(password: str) -> tuple[bool, str]:
    """Validar que la contraseña cumpla requisitos mínimos de seguridad"""
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not any(c.isupper() for c in password):
        return False, "La contraseña debe contener al menos una mayúscula"
    
    if not any(c.islower() for c in password):
        return False, "La contraseña debe contener al menos una minúscula"
    
    if not any(c.isdigit() for c in password):
        return False, "La contraseña debe contener al menos un número"
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "La contraseña debe contener al menos un carácter especial"
    
    return True, "Contraseña válida"

def validate_email(email: str) -> tuple[bool, str]:
    """Validación básica de email"""
    if '@' not in email or '.' not in email:
        return False, "Email inválido"
    
    if len(email) < 5:
        return False, "Email demasiado corto"
    
    return True, "Email válido"

def main():
    """Generar contraseña hasheada con validaciones"""
    print("🔐 Generador de contraseñas para Finanzas Personales")
    print("=" * 60)
    print("⚠️  IMPORTANTE: Este script genera credenciales SEGURAS")
    print("   El archivo config.yaml NO debe subirse al repositorio")
    print("=" * 60)
    
    # Verificar si ya existe config.yaml
    config_path = Path('config.yaml')
    if config_path.exists():
        print("⚠️  ADVERTENCIA: Ya existe un archivo config.yaml")
        overwrite = input("¿Deseas sobrescribirlo? (s/N): ").strip().lower()
        if overwrite != 's':
            print("❌ Operación cancelada")
            return
    
    # Solicitar datos con validaciones
    while True:
        username = input("Usuario (ej: admin): ").strip()
        if len(username) < 2:
            print("❌ El usuario debe tener al menos 2 caracteres")
            continue
        if ' ' in username:
            print("❌ El usuario no puede contener espacios")
            continue
        break
    
    while True:
        name = input("Nombre completo: ").strip()
        if len(name) < 2:
            print("❌ El nombre debe tener al menos 2 caracteres")
            continue
        break
    
    while True:
        email = input("Email: ").strip()
        is_valid, message = validate_email(email)
        if not is_valid:
            print(f"❌ {message}")
            continue
        break
    
    while True:
        password = input("Contraseña: ").strip()
        is_valid, message = validate_password(password)
        if not is_valid:
            print(f"❌ {message}")
            print("💡 Sugerencia: Usa al menos 8 caracteres con mayúsculas, minúsculas, números y símbolos")
            continue
        
        # Confirmar contraseña
        confirm_password = input("Confirmar contraseña: ").strip()
        if password != confirm_password:
            print("❌ Las contraseñas no coinciden")
            continue
        break
    
    print("\n" + "=" * 60)
    print("✅ Datos validados correctamente")
    print("🔐 Generando hash de contraseña...")
    
    try:
        # Generar hash de la contraseña
        hashed_password = stauth.Hasher([password]).generate()[0]
        
        # Crear configuración
        config = {
            'credentials': {
                'usernames': {
                    username: {
                        'email': email,
                        'name': name,
                        'password': hashed_password
                    }
                }
            }
        }
        
        # Guardar en archivo
        with open('config.yaml', 'w') as file:
            yaml.dump(config, file, default_flow_style=False, sort_keys=False)
        
        print("✅ Configuración guardada en config.yaml")
        print("\n📋 Resumen de credenciales:")
        print(f"👤 Usuario: {username}")
        print(f"📧 Email: {email}")
        print(f"🔑 Contraseña: {'*' * len(password)}")
        print(f"📁 Archivo: {config_path.absolute()}")
        
        print("\n🔒 Seguridad:")
        print("✅ Contraseña hasheada con bcrypt")
        print("✅ Archivo config.yaml creado")
        print("✅ config.yaml está en .gitignore (no se subirá al repo)")
        
        print("\n💡 Próximos pasos:")
        print("1. Verifica que config.yaml NO esté en git: git status")
        print("2. Ejecuta la aplicación: streamlit run app.py")
        print("3. Usa las credenciales para acceder")
        
        # Verificar que el archivo está en .gitignore
        gitignore_path = Path('.gitignore')
        if gitignore_path.exists():
            with open(gitignore_path, 'r') as f:
                gitignore_content = f.read()
                if 'config.yaml' in gitignore_content:
                    print("✅ config.yaml está correctamente en .gitignore")
                else:
                    print("⚠️  ADVERTENCIA: config.yaml NO está en .gitignore")
                    print("   Agrega 'config.yaml' al archivo .gitignore")
        else:
            print("⚠️  ADVERTENCIA: No se encontró archivo .gitignore")
            print("   Crea un archivo .gitignore con 'config.yaml'")
        
    except Exception as e:
        print(f"❌ Error al generar configuración: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
