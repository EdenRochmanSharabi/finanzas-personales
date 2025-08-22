#!/usr/bin/env python3
"""
Script de configuración inicial para Finanzas Personales
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

def check_python_version():
    """Verifica que la versión de Python sea compatible"""
    if sys.version_info < (3, 8):
        print("❌ Error: Se requiere Python 3.8 o superior")
        print(f"   Versión actual: {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]} - Compatible")

def create_virtual_environment():
    """Crea un entorno virtual si no existe"""
    venv_path = Path("venv")
    if venv_path.exists():
        print("✅ Entorno virtual ya existe")
        return
    
    print("🔧 Creando entorno virtual...")
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print("✅ Entorno virtual creado")
    except subprocess.CalledProcessError:
        print("❌ Error al crear el entorno virtual")
        sys.exit(1)

def install_dependencies():
    """Instala las dependencias del proyecto"""
    print("📦 Instalando dependencias...")
    
    # Determinar el comando de pip según el sistema operativo
    if os.name == 'nt':  # Windows
        pip_cmd = "venv\\Scripts\\pip"
    else:  # Unix/Linux/macOS
        pip_cmd = "venv/bin/pip"
    
    try:
        subprocess.run([pip_cmd, "install", "-r", "requirements.txt"], check=True)
        print("✅ Dependencias instaladas")
    except subprocess.CalledProcessError:
        print("❌ Error al instalar dependencias")
        sys.exit(1)

def setup_config():
    """Configura el archivo de configuración"""
    config_file = Path("config.yaml")
    example_config = Path("config.example.yaml")
    
    if config_file.exists():
        print("✅ Archivo de configuración ya existe")
        return
    
    if example_config.exists():
        print("🔧 Copiando archivo de configuración de ejemplo...")
        shutil.copy(example_config, config_file)
        print("✅ Archivo config.yaml creado")
        print("⚠️  IMPORTANTE: Edita config.yaml con tus credenciales antes de usar la app")
    else:
        print("❌ No se encontró config.example.yaml")
        sys.exit(1)

def create_directories():
    """Crea directorios necesarios"""
    directories = [".streamlit"]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    
    print("✅ Directorios creados")

def main():
    """Función principal del script de setup"""
    print("🚀 Configurando Finanzas Personales...")
    print("=" * 50)
    
    # Verificar versión de Python
    check_python_version()
    
    # Crear directorios
    create_directories()
    
    # Crear entorno virtual
    create_virtual_environment()
    
    # Instalar dependencias
    install_dependencies()
    
    # Configurar archivo de configuración
    setup_config()
    
    print("=" * 50)
    print("✅ Configuración completada exitosamente!")
    print("\n📋 Próximos pasos:")
    print("1. Edita config.yaml con tus credenciales")
    print("2. Activa el entorno virtual:")
    if os.name == 'nt':  # Windows
        print("   venv\\Scripts\\activate")
    else:  # Unix/Linux/macOS
        print("   source venv/bin/activate")
    print("3. Ejecuta la aplicación:")
    print("   streamlit run app.py")
    print("\n🔒 Recuerda: Nunca subas config.yaml a GitHub")

if __name__ == "__main__":
    main()
