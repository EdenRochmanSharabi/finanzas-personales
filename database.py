# -*- coding: utf-8 -*-
"""
Módulo de base de datos para Finanzas Personales
Usa SQLAlchemy para manejar todas las tablas
"""

import sqlite3
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
import numpy as np
from pathlib import Path

Base = declarative_base()

# ----------------------------- Modelos de Base de Datos -----------------------------

class Config(Base):
    __tablename__ = 'config'
    
    id = Column(Integer, primary_key=True)
    clave = Column(String(100), unique=True, nullable=False)
    valor = Column(Text, nullable=True)
    tipo = Column(String(20), default='string')  # string, float, date, list

class Cuenta(Base):
    __tablename__ = 'cuentas'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), unique=True, nullable=False)
    saldo_inicial = Column(Float, default=0.0)
    activa = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

class Categoria(Base):
    __tablename__ = 'categorias'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), unique=True, nullable=False)
    activa = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

class Etiqueta(Base):
    __tablename__ = 'etiquetas'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), unique=True, nullable=False)
    activa = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

class Gasto(Base):
    __tablename__ = 'gastos'
    
    id = Column(Integer, primary_key=True)
    fecha = Column(DateTime, nullable=False)
    cuenta_id = Column(Integer, nullable=False)
    descripcion = Column(String(200), nullable=False)
    categoria_id = Column(Integer, nullable=True)
    tipo = Column(String(20), default='Variable')  # Fijo, Variable, Otro
    etiqueta_id = Column(Integer, nullable=True)
    importe = Column(Float, nullable=False)
    recurrente_id = Column(String(50), nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now)
    fecha_modificacion = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Ingreso(Base):
    __tablename__ = 'ingresos'
    
    id = Column(Integer, primary_key=True)
    fecha = Column(DateTime, nullable=False)
    cuenta_id = Column(Integer, nullable=False)
    descripcion = Column(String(200), nullable=False)
    fuente = Column(String(100), nullable=False)
    bruto = Column(Float, nullable=False)
    neto = Column(Float, nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.now)
    fecha_modificacion = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Transferencia(Base):
    __tablename__ = 'transferencias'
    
    id = Column(Integer, primary_key=True)
    fecha = Column(DateTime, nullable=False)
    cuenta_origen_id = Column(Integer, nullable=False)
    cuenta_destino_id = Column(Integer, nullable=False)
    importe = Column(Float, nullable=False)
    descripcion = Column(String(200), nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

class Recurrente(Base):
    __tablename__ = 'recurrentes'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    importe = Column(Float, nullable=False)
    periodicidad = Column(String(20), default='Mensual')  # Mensual, Semanal, etc.
    dia_mes = Column(Integer, default=1)
    cuenta_id = Column(Integer, nullable=True)
    categoria_id = Column(Integer, nullable=True)
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

class Inversion(Base):
    __tablename__ = 'inversiones'
    
    id = Column(Integer, primary_key=True)
    fecha = Column(DateTime, nullable=False)
    operacion = Column(String(20), nullable=False)  # Compra, Venta
    ticker = Column(String(20), nullable=False)
    tipo = Column(String(20), nullable=False)  # Accion, ETF, Cripto, etc.
    cantidad = Column(Float, nullable=False)
    precio = Column(Float, nullable=False)
    comisiones = Column(Float, default=0.0)
    cuenta_id = Column(Integer, nullable=True)
    etiqueta_id = Column(Integer, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

class Precio(Base):
    __tablename__ = 'precios'
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), unique=True, nullable=False)
    precio_actual = Column(Float, nullable=False)
    fecha_actualizacion = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# ----------------------------- Clase de Gestión de Base de Datos -----------------------------

class DatabaseManager:
    def __init__(self, db_path: str = "finanzas.db"):
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """Crear todas las tablas si no existen"""
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self) -> Session:
        """Obtener una sesión de base de datos"""
        return self.SessionLocal()
        
    def init_default_data(self):
        """Inicializar datos por defecto"""
        session = self.get_session()
        try:
            # Configuración por defecto
            configs = [
                {"clave": "Moneda", "valor": "EUR", "tipo": "string"},
                {"clave": "% Ahorro objetivo", "valor": "0.25", "tipo": "float"},
                {"clave": "% Fijos (necesidades)", "valor": "0.50", "tipo": "float"},
                {"clave": "% Variables (deseos)", "valor": "0.25", "tipo": "float"},
                {"clave": "Mes objetivo", "valor": datetime.now().strftime("%Y-%m-%d"), "tipo": "date"},
                {"clave": "Fuentes de ingreso", "valor": "Nomina", "tipo": "list"},
            ]
            
            for config in configs:
                existing = session.query(Config).filter_by(clave=config["clave"]).first()
                if not existing:
                    new_config = Config(**config)
                    session.add(new_config)
            
            # Categorías básicas
            categorias_basicas = [
                "Alimentación", "Transporte", "Vivienda", "Ocio", "Salud", 
                "Educación", "Ropa", "Servicios", "Otros"
            ]
            
            for cat in categorias_basicas:
                existing = session.query(Categoria).filter_by(nombre=cat).first()
                if not existing:
                    new_cat = Categoria(nombre=cat)
                    session.add(new_cat)
            
            # Etiquetas básicas
            etiquetas_basicas = ["Urgente", "Lujo", "Necesario", "Inversión"]
            
            for etq in etiquetas_basicas:
                existing = session.query(Etiqueta).filter_by(nombre=etq).first()
                if not existing:
                    new_etq = Etiqueta(nombre=etq)
                    session.add(new_etq)
            
            session.commit()
            
        except SQLAlchemyError as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def migrate_from_excel(self, excel_path: str):
        """Migrar datos desde Excel a la base de datos"""
        if not Path(excel_path).exists():
            raise FileNotFoundError(f"No se encontró el archivo Excel: {excel_path}")
            
        session = self.get_session()
        try:
            # Leer Excel
            with pd.ExcelFile(excel_path) as xl:
                # Migrar configuración
                if "Config" in xl.sheet_names:
                    config_df = xl.parse("Config")
                    for _, row in config_df.iterrows():
                        if pd.notna(row.iloc[0]) and pd.notna(row.iloc[1]):
                            clave = str(row.iloc[0]).strip()
                            valor = str(row.iloc[1]).strip()
                            existing = session.query(Config).filter_by(clave=clave).first()
                            if not existing:
                                new_config = Config(clave=clave, valor=valor)
                                session.add(new_config)
                
                # Migrar cuentas
                if "Cuentas" in xl.sheet_names:
                    cuentas_df = xl.parse("Cuentas")
                    for _, row in cuentas_df.iterrows():
                        if pd.notna(row.get("Cuenta")):
                            nombre = str(row["Cuenta"]).strip()
                            saldo = float(row.get("Saldo inicial", 0))
                            existing = session.query(Cuenta).filter_by(nombre=nombre).first()
                            if not existing:
                                new_cuenta = Cuenta(nombre=nombre, saldo_inicial=saldo)
                                session.add(new_cuenta)
                
                # Migrar categorías
                if "Categorias" in xl.sheet_names:
                    cat_df = xl.parse("Categorias")
                    for _, row in cat_df.iterrows():
                        if pd.notna(row.get("Categoria")):
                            nombre = str(row["Categoria"]).strip()
                            existing = session.query(Categoria).filter_by(nombre=nombre).first()
                            if not existing:
                                new_cat = Categoria(nombre=nombre)
                                session.add(new_cat)
                
                # Migrar etiquetas
                if "Etiquetas" in xl.sheet_names:
                    etq_df = xl.parse("Etiquetas")
                    for _, row in etq_df.iterrows():
                        if pd.notna(row.get("Etiqueta")):
                            nombre = str(row["Etiqueta"]).strip()
                            existing = session.query(Etiqueta).filter_by(nombre=nombre).first()
                            if not existing:
                                new_etq = Etiqueta(nombre=nombre)
                                session.add(new_etq)
                
                # Migrar gastos
                if "Gastos" in xl.sheet_names:
                    gastos_df = xl.parse("Gastos")
                    for _, row in gastos_df.iterrows():
                        if pd.notna(row.get("Fecha")) and pd.notna(row.get("Importe")):
                            # Buscar cuenta
                            cuenta_nombre = str(row.get("Cuenta", "")).strip()
                            cuenta = session.query(Cuenta).filter_by(nombre=cuenta_nombre).first()
                            if not cuenta:
                                cuenta = Cuenta(nombre=cuenta_nombre)
                                session.add(cuenta)
                                session.flush()
                            
                            # Buscar categoría
                            cat_nombre = str(row.get("Categoria", "")).strip()
                            categoria = None
                            if cat_nombre and cat_nombre != "nan":
                                categoria = session.query(Categoria).filter_by(nombre=cat_nombre).first()
                                if not categoria:
                                    categoria = Categoria(nombre=cat_nombre)
                                    session.add(categoria)
                                    session.flush()
                            
                            # Buscar etiqueta
                            etq_nombre = str(row.get("Etiqueta", "")).strip()
                            etiqueta = None
                            if etq_nombre and etq_nombre != "nan":
                                etiqueta = session.query(Etiqueta).filter_by(nombre=etq_nombre).first()
                                if not etiqueta:
                                    etiqueta = Etiqueta(nombre=etq_nombre)
                                    session.add(etiqueta)
                                    session.flush()
                            
                            new_gasto = Gasto(
                                fecha=pd.to_datetime(row["Fecha"]),
                                cuenta_id=cuenta.id,
                                descripcion=str(row.get("Descripcion", "")),
                                categoria_id=categoria.id if categoria else None,
                                tipo=str(row.get("Tipo", "Variable")),
                                etiqueta_id=etiqueta.id if etiqueta else None,
                                importe=float(row["Importe"]),
                                recurrente_id=str(row.get("Recurrente", "")) if pd.notna(row.get("Recurrente")) else None
                            )
                            session.add(new_gasto)
                
                # Migrar ingresos
                if "Ingresos" in xl.sheet_names:
                    ingresos_df = xl.parse("Ingresos")
                    for _, row in ingresos_df.iterrows():
                        if pd.notna(row.get("Fecha")) and pd.notna(row.get("Neto")):
                            # Buscar cuenta
                            cuenta_nombre = str(row.get("Cuenta", "")).strip()
                            cuenta = session.query(Cuenta).filter_by(nombre=cuenta_nombre).first()
                            if not cuenta:
                                cuenta = Cuenta(nombre=cuenta_nombre)
                                session.add(cuenta)
                                session.flush()
                            
                            new_ingreso = Ingreso(
                                fecha=pd.to_datetime(row["Fecha"]),
                                cuenta_id=cuenta.id,
                                descripcion=str(row.get("Descripcion", "")),
                                fuente=str(row.get("Fuente", "")),
                                bruto=float(row.get("Bruto", 0)),
                                neto=float(row["Neto"])
                            )
                            session.add(new_ingreso)
                
                # Migrar transferencias
                if "Transferencias" in xl.sheet_names:
                    transf_df = xl.parse("Transferencias")
                    for _, row in transf_df.iterrows():
                        if pd.notna(row.get("Fecha")) and pd.notna(row.get("Importe")):
                            # Buscar cuentas
                            desde_nombre = str(row.get("Desde", "")).strip()
                            hacia_nombre = str(row.get("Hacia", "")).strip()
                            
                            desde = session.query(Cuenta).filter_by(nombre=desde_nombre).first()
                            if not desde:
                                desde = Cuenta(nombre=desde_nombre)
                                session.add(desde)
                                session.flush()
                            
                            hacia = session.query(Cuenta).filter_by(nombre=hacia_nombre).first()
                            if not hacia:
                                hacia = Cuenta(nombre=hacia_nombre)
                                session.add(hacia)
                                session.flush()
                            
                            new_transf = Transferencia(
                                fecha=pd.to_datetime(row["Fecha"]),
                                cuenta_origen_id=desde.id,
                                cuenta_destino_id=hacia.id,
                                importe=float(row["Importe"]),
                                descripcion=str(row.get("Descripcion", ""))
                            )
                            session.add(new_transf)
                
                # Migrar recurrentes
                if "Recurrentes" in xl.sheet_names:
                    recur_df = xl.parse("Recurrentes")
                    for _, row in recur_df.iterrows():
                        if pd.notna(row.get("Nombre")) and pd.notna(row.get("Importe")):
                            # Buscar cuenta
                            cuenta_nombre = str(row.get("Cuenta origen", "")).strip()
                            cuenta = None
                            if cuenta_nombre and cuenta_nombre != "nan":
                                cuenta = session.query(Cuenta).filter_by(nombre=cuenta_nombre).first()
                                if not cuenta:
                                    cuenta = Cuenta(nombre=cuenta_nombre)
                                    session.add(cuenta)
                                    session.flush()
                            
                            # Buscar categoría
                            cat_nombre = str(row.get("Categoria sugerida", "")).strip()
                            categoria = None
                            if cat_nombre and cat_nombre != "nan":
                                categoria = session.query(Categoria).filter_by(nombre=cat_nombre).first()
                                if not categoria:
                                    categoria = Categoria(nombre=cat_nombre)
                                    session.add(categoria)
                                    session.flush()
                            
                            new_recur = Recurrente(
                                nombre=str(row["Nombre"]),
                                importe=float(row["Importe"]),
                                periodicidad=str(row.get("Periodicidad", "Mensual")),
                                dia_mes=int(row.get("Dia del mes", 1)),
                                cuenta_id=cuenta.id if cuenta else None,
                                categoria_id=categoria.id if categoria else None
                            )
                            session.add(new_recur)
                
                # Migrar inversiones
                if "Inversiones" in xl.sheet_names:
                    inv_df = xl.parse("Inversiones")
                    for _, row in inv_df.iterrows():
                        if pd.notna(row.get("Fecha")) and pd.notna(row.get("Ticker")):
                            # Buscar cuenta
                            cuenta_nombre = str(row.get("Cuenta", "")).strip()
                            cuenta = None
                            if cuenta_nombre and cuenta_nombre != "nan":
                                cuenta = session.query(Cuenta).filter_by(nombre=cuenta_nombre).first()
                                if not cuenta:
                                    cuenta = Cuenta(nombre=cuenta_nombre)
                                    session.add(cuenta)
                                    session.flush()
                            
                            # Buscar etiqueta
                            etq_nombre = str(row.get("Etiqueta", "")).strip()
                            etiqueta = None
                            if etq_nombre and etq_nombre != "nan":
                                etiqueta = session.query(Etiqueta).filter_by(nombre=etq_nombre).first()
                                if not etiqueta:
                                    etiqueta = Etiqueta(nombre=etq_nombre)
                                    session.add(etiqueta)
                                    session.flush()
                            
                            new_inv = Inversion(
                                fecha=pd.to_datetime(row["Fecha"]),
                                operacion=str(row.get("Operacion", "Compra")),
                                ticker=str(row["Ticker"]),
                                tipo=str(row.get("Tipo", "ETF")),
                                cantidad=float(row.get("Cantidad", 0)),
                                precio=float(row.get("Precio", 0)),
                                comisiones=float(row.get("Comisiones", 0)),
                                cuenta_id=cuenta.id if cuenta else None,
                                etiqueta_id=etiqueta.id if etiqueta else None
                            )
                            session.add(new_inv)
                
                # Migrar precios
                if "Precios" in xl.sheet_names:
                    precios_df = xl.parse("Precios")
                    for _, row in precios_df.iterrows():
                        if pd.notna(row.get("Ticker")) and pd.notna(row.get("Precio actual")):
                            new_precio = Precio(
                                ticker=str(row["Ticker"]),
                                precio_actual=float(row["Precio actual"])
                            )
                            session.add(new_precio)
            
            session.commit()
            return True
            
        except SQLAlchemyError as e:
            session.rollback()
            raise e
        finally:
            session.close()

# ----------------------------- Funciones de utilidad -----------------------------

def get_config_value(session: Session, clave: str, default: Any = None) -> Any:
    """Obtener valor de configuración"""
    config = session.query(Config).filter_by(clave=clave).first()
    if not config:
        return default
    
    if config.tipo == "float":
        return float(config.valor)
    elif config.tipo == "date":
        return pd.to_datetime(config.valor).date()
    elif config.tipo == "list":
        return config.valor.split(",") if config.valor else []
    else:
        return config.valor

def set_config_value(session: Session, clave: str, valor: Any, tipo: str = "string"):
    """Establecer valor de configuración"""
    config = session.query(Config).filter_by(clave=clave).first()
    if config:
        config.valor = str(valor)
        config.tipo = tipo
    else:
        new_config = Config(clave=clave, valor=str(valor), tipo=tipo)
        session.add(new_config)
    session.commit()

def get_cuenta_by_name(session: Session, nombre: str) -> Optional[Cuenta]:
    """Obtener cuenta por nombre"""
    return session.query(Cuenta).filter_by(nombre=nombre).first()

def get_categoria_by_name(session: Session, nombre: str) -> Optional[Categoria]:
    """Obtener categoría por nombre"""
    return session.query(Categoria).filter_by(nombre=nombre).first()

def get_etiqueta_by_name(session: Session, nombre: str) -> Optional[Etiqueta]:
    """Obtener etiqueta por nombre"""
    return session.query(Etiqueta).filter_by(nombre=nombre).first()

