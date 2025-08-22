#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de verificación de seguridad para Finanzas Personales
Ejecutar: python security_check.py

Este script verifica que la configuración de seguridad esté correcta
antes de hacer deploy o usar la aplicación en producción.
"""

import os
import sys
import yaml
from pathlib import Path
import subprocess

def check_git_status():
    """Verificar que config.yaml no esté en el repositorio"""
    print("🔍 Verificando estado de Git...")
    
    try:
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True, check=True)
        
        if 'config.yaml' in result.stdout:
            print("❌ ERROR: config.yaml está en el repositorio Git")
            print("   Ejecuta: git rm --cached config.yaml")
            return False
        else:
            print("✅ config.yaml NO está en el repositorio")
            return True
    except subprocess.CalledProcessError:
        print("⚠️  No se pudo verificar Git (¿estás en un repositorio?)")
        return True

def check_gitignore():
    """Verificar que config.yaml esté en .gitignore"""
    print("🔍 Verificando .gitignore...")
    
    gitignore_path = Path('.gitignore')
    if not gitignore_path.exists():
        print("❌ ERROR: No existe archivo .gitignore")
        return False
    
    with open(gitignore_path, 'r') as f:
        content = f.read()
        
    if 'config.yaml' in content:
        print("✅ config.yaml está en .gitignore")
        return True
    else:
        print("❌ ERROR: config.yaml NO está en .gitignore")
        print("   Agrega 'config.yaml' al archivo .gitignore")
        return False

def check_config_file():
    """Verificar que config.yaml existe y es válido"""
    print("🔍 Verificando config.yaml...")
    
    config_path = Path('config.yaml')
    if not config_path.exists():
        print("❌ ERROR: No existe config.yaml")
        print("   Ejecuta: python generate_password.py")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Verificar estructura
        if 'credentials' not in config:
            print("❌ ERROR: config.yaml no tiene estructura válida")
            return False
        
        if 'usernames' not in config['credentials']:
            print("❌ ERROR: config.yaml no tiene sección usernames")
            return False
        
        users = config['credentials']['usernames']
        if not users:
            print("❌ ERROR: No hay usuarios configurados")
            return False
        
        # Verificar cada usuario
        for username, user_data in users.items():
            required_fields = ['name', 'email', 'password']
            for field in required_fields:
                if field not in user_data:
                    print(f"❌ ERROR: Usuario '{username}' no tiene campo '{field}'")
                    return False
            
            # Verificar que la contraseña esté hasheada
            password = user_data['password']
            if not password.startswith('$2b$'):
                print(f"❌ ERROR: Contraseña de '{username}' no está hasheada con bcrypt")
                return False
        
        print(f"✅ config.yaml válido con {len(users)} usuario(s)")
        return True
        
    except yaml.YAMLError as e:
        print(f"❌ ERROR: config.yaml no es un YAML válido: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR al leer config.yaml: {e}")
        return False

def check_dependencies():
    """Verificar que las dependencias estén instaladas"""
    print("🔍 Verificando dependencias...")
    
    required_packages = [
        'streamlit',
        'pandas', 
        'sqlalchemy',
        'bcrypt',
        'yaml',
        'streamlit_authenticator'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - NO INSTALADO")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n❌ Faltan dependencias: {', '.join(missing_packages)}")
        print("   Ejecuta: pip install -r requirements.txt")
        return False
    
    return True

def check_security_files():
    """Verificar que no existan archivos con contraseñas en texto plano"""
    print("🔍 Verificando archivos de seguridad...")
    
    dangerous_files = [
        'hash_password.py',
        'password.txt',
        'credentials.txt',
        'secrets.txt'
    ]
    
    found_dangerous = []
    
    for file_name in dangerous_files:
        if Path(file_name).exists():
            print(f"❌ ARCHIVO PELIGROSO: {file_name}")
            found_dangerous.append(file_name)
    
    if found_dangerous:
        print(f"\n⚠️  ADVERTENCIA: Se encontraron archivos con posibles credenciales:")
        for file_name in found_dangerous:
            print(f"   - {file_name}")
        print("   Elimina estos archivos antes de hacer deploy")
        return False
    
    print("✅ No se encontraron archivos peligrosos")
    return True

def main():
    """Ejecutar todas las verificaciones de seguridad"""
    print("🔒 Verificación de Seguridad - Finanzas Personales")
    print("=" * 60)
    
    checks = [
        ("Git Status", check_git_status),
        (".gitignore", check_gitignore),
        ("config.yaml", check_config_file),
        ("Dependencias", check_dependencies),
        ("Archivos de Seguridad", check_security_files)
    ]
    
    results = []
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"❌ Error en verificación: {e}")
            results.append((check_name, False))
    
    # Resumen final
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE VERIFICACIÓN:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASÓ" if result else "❌ FALLÓ"
        print(f"   {check_name}: {status}")
    
    print(f"\n🎯 Resultado: {passed}/{total} verificaciones pasaron")
    
    if passed == total:
        print("🎉 ¡Todas las verificaciones de seguridad pasaron!")
        print("   La aplicación está lista para usar/deploy")
        return True
    else:
        print("⚠️  Algunas verificaciones fallaron")
        print("   Corrige los problemas antes de usar la aplicación")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
