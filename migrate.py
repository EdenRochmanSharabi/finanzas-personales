#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de migración para actualizar la base de datos existente
con las nuevas tablas y funcionalidades.
"""

import sqlite3
import os
from pathlib import Path

def migrate_database():
    """Migra la base de datos existente a la nueva estructura"""
    
    db_path = "finanzas.db"
    
    if not os.path.exists(db_path):
        print("❌ No se encontró la base de datos finanzas.db")
        print("💡 Ejecuta primero la aplicación para crear la base de datos")
        return False
    
    print("🔄 Iniciando migración de la base de datos...")
    
    try:
        # Conectar a la base de datos
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar si las nuevas tablas ya existen
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='objetivos'")
        if cursor.fetchone():
            print("✅ Las nuevas tablas ya existen.")
        else:
            print("📋 Creando nuevas tablas...")
            
            # Crear tabla de objetivos
            cursor.execute("""
                CREATE TABLE objetivos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre VARCHAR(100) NOT NULL,
                    tipo VARCHAR(20) NOT NULL,
                    objetivo_id INTEGER,
                    importe_objetivo FLOAT NOT NULL,
                    periodo VARCHAR(20) DEFAULT 'Mensual',
                    activo BOOLEAN DEFAULT 1,
                    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                    fecha_modificacion DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Crear tabla de sobres
            cursor.execute("""
                CREATE TABLE sobres (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre VARCHAR(100) NOT NULL,
                    descripcion VARCHAR(200),
                    importe_objetivo FLOAT NOT NULL,
                    importe_actual FLOAT DEFAULT 0.0,
                    permite_rollover BOOLEAN DEFAULT 1,
                    activo BOOLEAN DEFAULT 1,
                    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                    fecha_modificacion DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            print("📝 Insertando datos por defecto...")
            
            # Insertar objetivos básicos
            objetivos_basicos = [
                ("Ahorro General", "general", None, 1000.0, "Mensual"),
                ("Emergencias", "general", None, 500.0, "Mensual"),
            ]
            
            for nombre, tipo, objetivo_id, importe, periodo in objetivos_basicos:
                cursor.execute("""
                    INSERT INTO objetivos (nombre, tipo, objetivo_id, importe_objetivo, periodo)
                    VALUES (?, ?, ?, ?, ?)
                """, (nombre, tipo, objetivo_id, importe, periodo))
            
            # Insertar sobres básicos
            sobres_basicos = [
                ("Vacaciones", "Ahorro para viajes", 200.0),
                ("Regalos", "Presupuesto para regalos", 100.0),
                ("Mantenimiento", "Reparaciones del hogar", 150.0),
            ]
            
            for nombre, descripcion, importe in sobres_basicos:
                cursor.execute("""
                    INSERT INTO sobres (nombre, descripcion, importe_objetivo)
                    VALUES (?, ?, ?)
                """, (nombre, descripcion, importe))
        
        # Verificar si la columna cuenta_id existe en la tabla sobres
        cursor.execute("PRAGMA table_info(sobres)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'cuenta_id' not in columns:
            print("🔧 Añadiendo columna cuenta_id a la tabla sobres...")
            cursor.execute("ALTER TABLE sobres ADD COLUMN cuenta_id INTEGER REFERENCES cuentas(id)")
        
        print("📊 Creando índices para mejorar rendimiento...")
        
        # Crear índices en la tabla gastos
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gastos_cuenta_id ON gastos(cuenta_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gastos_fecha_cuenta ON gastos(fecha, cuenta_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gastos_categoria_fecha ON gastos(categoria_id, fecha)")
        
        # Crear índices en la tabla ingresos
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ingresos_fecha ON ingresos(fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ingresos_cuenta_id ON ingresos(cuenta_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ingresos_fecha_cuenta ON ingresos(fecha, cuenta_id)")
        
        # Crear índices en la tabla transferencias
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transferencias_fecha ON transferencias(fecha)")
        
        # Insertar configuraciones adicionales
        configs_adicionales = [
            ("Validar presupuesto 100%", "true", "string"),
            ("Auto-corregir presupuesto", "false", "string"),
            ("Ahorro automático mensual", "500.0", "float"),
            ("Objetivo gastos fijos", "0.0", "float"),
            ("Objetivo gastos variables", "0.0", "float"),
        ]
        
        for clave, valor, tipo in configs_adicionales:
            cursor.execute("""
                INSERT OR IGNORE INTO config (clave, valor, tipo)
                VALUES (?, ?, ?)
            """, (clave, valor, tipo))
        
        # Commit de los cambios
        conn.commit()
        
        print("✅ Migración completada exitosamente!")
        print("📊 Nuevas funcionalidades disponibles:")
        print("   • Objetivos y metas de ahorro")
        print("   • Presupuesto por sobres (sinking funds)")
        print("   • Análisis temporal mejorado")
        print("   • Exportación de datos")
        print("   • Sistema de deshacer acciones")
        print("   • Validación de presupuesto")
        print("   • Columna cuenta_id en sobres")
        
        return True
        
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

def backup_database():
    """Crea un backup de la base de datos antes de migrar"""
    
    db_path = "finanzas.db"
    backup_path = "finanzas_backup.db"
    
    if not os.path.exists(db_path):
        print("❌ No se encontró la base de datos para hacer backup")
        return False
    
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"💾 Backup creado: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Error al crear backup: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Script de migración de Finanzas Personales")
    print("=" * 50)
    
    # Crear backup
    if backup_database():
        print("✅ Backup creado exitosamente")
    else:
        print("⚠️ No se pudo crear backup, continuando...")
    
    # Ejecutar migración
    if migrate_database():
        print("\n🎉 ¡Migración completada!")
        print("💡 Ahora puedes ejecutar la aplicación con las nuevas funcionalidades")
    else:
        print("\n❌ La migración falló")
        print("💡 Verifica que tienes permisos de escritura en el directorio")
