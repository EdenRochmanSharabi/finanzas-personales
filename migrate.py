#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de migración desde Excel a Base de Datos SQL
Ejecutar: python migrate.py [archivo_excel]
"""

import sys
from pathlib import Path
from database import DatabaseManager

def main():
    """Función principal de migración"""
    print("🔄 Migración de Excel a Base de Datos SQL")
    print("=" * 50)
    
    # Obtener archivo Excel
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        # Buscar archivos Excel en el directorio actual
        excel_files = list(Path(".").glob("*.xlsx"))
        if not excel_files:
            print("❌ No se encontraron archivos Excel en el directorio actual")
            print("Uso: python migrate.py [ruta_al_excel]")
            return
        
        if len(excel_files) == 1:
            excel_path = str(excel_files[0])
        else:
            print("📁 Archivos Excel encontrados:")
            for i, file in enumerate(excel_files, 1):
                print(f"  {i}. {file.name}")
            try:
                choice = int(input("Selecciona el archivo a migrar (número): ")) - 1
                excel_path = str(excel_files[choice])
            except (ValueError, IndexError):
                print("❌ Selección inválida")
                return
    
    # Verificar que el archivo existe
    if not Path(excel_path).exists():
        print(f"❌ No se encontró el archivo: {excel_path}")
        return
    
    print(f"📊 Migrando: {excel_path}")
    
    # Inicializar base de datos
    db_manager = DatabaseManager("finanzas.db")
    db_manager.create_tables()
    db_manager.init_default_data()
    
    try:
        # Realizar migración
        db_manager.migrate_from_excel(excel_path)
        print("✅ Migración completada exitosamente!")
        print(f"📁 Base de datos creada: finanzas.db")
        print("\n🚀 Para ejecutar la aplicación:")
        print("   streamlit run app.py")
        
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
        return

if __name__ == "__main__":
    main()
