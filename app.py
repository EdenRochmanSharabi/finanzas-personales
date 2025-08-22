# -*- coding: utf-8 -*-
"""
Aplicación de Finanzas Personales
=================================

Esta aplicación permite gestionar finanzas personales usando una base de datos SQL
en lugar de archivos Excel. Proporciona una interfaz web moderna y funcionalidades
completas para el seguimiento de gastos, ingresos y análisis financiero.

Características principales:
- Base de datos SQLite para almacenamiento robusto
- Migración automática desde archivos Excel existentes
- Interfaz web con Streamlit
- Análisis de KPIs en tiempo real
- Gestión de categorías y etiquetas
- Presupuesto por bloques (50/30/20)
- Presupuesto por sobres
- Presupuesto por sobres (sinking funds)
- Sistema de deshacer acciones

Autor: Sistema de Finanzas Personales
Fecha: 2024
"""

import streamlit as st
import pandas as pd
import numpy as np
import calendar
import io
import yaml
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from database import DatabaseManager, get_config_value, set_config_value
from database import Gasto, Ingreso, Transferencia, Recurrente, Inversion, Precio
from database import Cuenta, Categoria, Etiqueta, Config, Sobre
from sqlalchemy import func

# Importar para autenticación
import hashlib

# =============================================================================
# FUNCIONES HELPER
# =============================================================================

def generate_unique_key(prefix: str, identifier: str, section: str = "") -> str:
    """
    Genera una clave única para elementos de Streamlit.
    
    Args:
        prefix (str): Prefijo del tipo de elemento
        identifier (str): Identificador único
        section (str): Sección de la aplicación (opcional)
        
    Returns:
        str: Clave única
    """
    if section:
        return f"{section}_{prefix}_{identifier}"
    return f"{prefix}_{identifier}"

# =============================================================================
# MODELOS DE DATOS
# =============================================================================

@dataclass
class KPIMetrics:
    """Modelo de datos para métricas financieras del mes"""
    ingresos_netos: float
    gastos_totales: float
    ahorro_neto: float
    tasa_ahorro: float
    objetivo_ahorro: float
    objetivo_fijos: float
    objetivo_variables: float
    actual_fijos: float
    actual_variables: float

@dataclass
class BudgetBlock:
    """Modelo de datos para bloques de presupuesto"""
    nombre: str
    objetivo: float
    actual: float
    desviacion: float

@dataclass
class TemporalData:
    """Modelo de datos para análisis temporal"""
    fecha: str
    ingresos: float
    gastos: float
    ahorro: float

@dataclass
class UndoAction:
    """Modelo para acciones de deshacer"""
    action_type: str  # 'delete_gasto', 'delete_ingreso', etc.
    data: Dict[str, Any]  # Datos para restaurar
    timestamp: datetime

# =============================================================================
# CLASE PRINCIPAL DE LA APLICACIÓN
# =============================================================================

class FinanzasApp:
    """
    Clase principal que maneja toda la lógica de la aplicación de finanzas.
    
    Esta clase encapsula:
    - Gestión de la base de datos
    - Cálculos financieros
    - Operaciones CRUD
    - Migración de datos
    - Sistema de deshacer
    
    Attributes:
        db_manager (DatabaseManager): Gestor de la base de datos
        config (Dict[str, Any]): Configuración actual de la aplicación
        undo_stack (List[UndoAction]): Pila de acciones para deshacer
    """
    
    def __init__(self, db_path: str = "finanzas.db"):
        """
        Inicializa la aplicación de finanzas.
        
        Args:
            db_path (str): Ruta al archivo de base de datos SQLite
        """
        self.db_manager = DatabaseManager(db_path)
        self.db_manager.create_tables()
        self.db_manager.init_default_data()
        self._config = None  # Cache de configuración
        self.undo_stack = []  # Pila de acciones para deshacer
    
    def get_session(self):
        """
        Obtiene una sesión de base de datos.
        
        Returns:
            Session: Sesión de SQLAlchemy para operaciones de BD
        """
        return self.db_manager.get_session()
    
    @property
    def config(self) -> Dict[str, Any]:
        """
        Obtiene la configuración actual de la aplicación.
        
        Returns:
            Dict[str, Any]: Diccionario con la configuración actual
        """
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Carga la configuración desde la base de datos.
        
        Returns:
            Dict[str, Any]: Configuración cargada
        """
        session = self.get_session()
        try:
            config = {
                "Moneda": get_config_value(session, "Moneda", "EUR"),
                "% Ahorro objetivo": get_config_value(session, "% Ahorro objetivo", 0.25),
                "% Fijos (necesidades)": get_config_value(session, "% Fijos (necesidades)", 0.50),
                "% Variables (deseos)": get_config_value(session, "% Variables (deseos)", 0.25),
                "Mes objetivo": get_config_value(session, "Mes objetivo", date.today()),
                "Fuentes de ingreso": get_config_value(session, "Fuentes de ingreso", ["Nomina"]),
                "Validar presupuesto 100%": get_config_value(session, "Validar presupuesto 100%", "true"),
                "Auto-corregir presupuesto": get_config_value(session, "Auto-corregir presupuesto", "false"),
                "Ahorro automático mensual": get_config_value(session, "Ahorro automático mensual", 500.0),
                "Objetivo gastos fijos": get_config_value(session, "Objetivo gastos fijos", 0.0),
                "Objetivo gastos variables": get_config_value(session, "Objetivo gastos variables", 0.0),
            }
            return config
        finally:
            session.close()
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        Guarda la configuración en la base de datos.
        
        Args:
            config (Dict[str, Any]): Nueva configuración a guardar
            
        Returns:
            bool: True si se guardó correctamente, False en caso contrario
        """
        session = self.get_session()
        try:
            for clave, valor in config.items():
                if clave == "Moneda":
                    set_config_value(session, clave, valor, "string")
                elif clave in ["% Ahorro objetivo", "% Fijos (necesidades)", "% Variables (deseos)", "Ahorro automático mensual", "Objetivo gastos fijos", "Objetivo gastos variables"]:
                    set_config_value(session, clave, valor, "float")
                elif clave == "Mes objetivo":
                    set_config_value(session, clave, valor, "date")
                elif clave == "Fuentes de ingreso":
                    set_config_value(session, clave, ",".join(valor) if isinstance(valor, list) else valor, "list")
                else:
                    set_config_value(session, clave, str(valor).lower(), "string")
            
            # Actualizar cache
            self._config = config
            return True
        except Exception as e:
            st.error(f"Error al guardar configuración: {e}")
            return False
        finally:
            session.close()
    
    def get_gastos_df(self, month_start: Optional[date] = None) -> pd.DataFrame:
        """
        Obtiene los gastos como DataFrame de pandas.
        
        Args:
            month_start (Optional[date]): Fecha de inicio del mes a filtrar.
                                        Si es None, obtiene todos los gastos.
        
        Returns:
            pd.DataFrame: DataFrame con los gastos, incluyendo joins con cuentas,
                         categorías y etiquetas
        """
        session = self.get_session()
        try:
            # Query principal con joins para obtener nombres en lugar de IDs
            query = session.query(
                Gasto.id,
                Gasto.fecha,
                Cuenta.nombre.label('Cuenta'),
                Gasto.descripcion,
                Categoria.nombre.label('Categoria'),
                Gasto.tipo,
                Etiqueta.nombre.label('Etiqueta'),
                Gasto.importe,
                Gasto.recurrente_id
            ).join(Cuenta, Gasto.cuenta_id == Cuenta.id)\
             .outerjoin(Categoria, Gasto.categoria_id == Categoria.id)\
             .outerjoin(Etiqueta, Gasto.etiqueta_id == Etiqueta.id)
            
            # Filtrar por mes si se especifica
            if month_start:
                start_dt = pd.Timestamp(month_start.year, month_start.month, 1)
                last_day = calendar.monthrange(month_start.year, month_start.month)[1]
                end_dt = pd.Timestamp(month_start.year, month_start.month, last_day, 23, 59, 59)
                query = query.filter(Gasto.fecha >= start_dt, Gasto.fecha <= end_dt)
            
            # Convertir a DataFrame
            df = pd.read_sql(query.statement, session.bind)
            return df
        finally:
            session.close()
    
    def get_ingresos_df(self, month_start: Optional[date] = None) -> pd.DataFrame:
        """
        Obtiene los ingresos como DataFrame de pandas.
        
        Args:
            month_start (Optional[date]): Fecha de inicio del mes a filtrar.
                                        Si es None, obtiene todos los ingresos.
        
        Returns:
            pd.DataFrame: DataFrame con los ingresos, incluyendo joins con cuentas
        """
        session = self.get_session()
        try:
            query = session.query(
                Ingreso.id,
                Ingreso.fecha,
                Cuenta.nombre.label('Cuenta'),
                Ingreso.descripcion,
                Ingreso.fuente,
                Ingreso.bruto,
                Ingreso.neto
            ).join(Cuenta, Ingreso.cuenta_id == Cuenta.id)
            
            # Filtrar por mes si se especifica
            if month_start:
                start_dt = pd.Timestamp(month_start.year, month_start.month, 1)
                last_day = calendar.monthrange(month_start.year, month_start.month)[1]
                end_dt = pd.Timestamp(month_start.year, month_start.month, last_day, 23, 59, 59)
                query = query.filter(Ingreso.fecha >= start_dt, Ingreso.fecha <= end_dt)
            
            df = pd.read_sql(query.statement, session.bind)
            return df
        finally:
            session.close()
    
    def get_cuentas_df(self) -> pd.DataFrame:
        """
        Obtiene las cuentas como DataFrame de pandas.
        
        Returns:
            pd.DataFrame: DataFrame con las cuentas y sus saldos
        """
        session = self.get_session()
        try:
            query = session.query(
                Cuenta.id,
                Cuenta.nombre,
                Cuenta.saldo_inicial,
                Cuenta.activa,
                Cuenta.fecha_creacion
            ).filter(Cuenta.activa == True)
            
            df = pd.read_sql(query.statement, session.bind)
            return df
        finally:
            session.close()
    
    def add_cuenta(self, nombre: str, saldo_inicial: float) -> bool:
        """
        Agrega una nueva cuenta a la base de datos.
        
        Args:
            nombre (str): Nombre de la cuenta
            saldo_inicial (float): Saldo inicial de la cuenta
        
        Returns:
            bool: True si se agregó correctamente, False en caso contrario
        """
        session = self.get_session()
        try:
            # Verificar si la cuenta ya existe
            existing = session.query(Cuenta).filter_by(nombre=nombre).first()
            if existing:
                st.error(f"La cuenta '{nombre}' ya existe")
                return False
            
            # Crear la cuenta
            nueva_cuenta = Cuenta(
                nombre=nombre,
                saldo_inicial=saldo_inicial,
                activa=True
            )
            session.add(nueva_cuenta)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al agregar cuenta: {e}")
            return False
        finally:
            session.close()
    
    def update_cuenta_saldo(self, cuenta_id: int, nuevo_saldo: float) -> bool:
        """
        Actualiza el saldo de una cuenta.
        
        Args:
            cuenta_id (int): ID de la cuenta a actualizar
            nuevo_saldo (float): Nuevo saldo de la cuenta
        
        Returns:
            bool: True si se actualizó correctamente, False en caso contrario
        """
        session = self.get_session()
        try:
            cuenta = session.query(Cuenta).filter_by(id=cuenta_id).first()
            if not cuenta:
                st.error("Cuenta no encontrada")
                return False
            
            cuenta.saldo_inicial = nuevo_saldo
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al actualizar saldo: {e}")
            return False
        finally:
            session.close()
    
    def delete_cuenta(self, cuenta_id: int) -> bool:
        """
        Desactiva una cuenta (borrado lógico).
        
        Args:
            cuenta_id (int): ID de la cuenta a desactivar
        
        Returns:
            bool: True si se desactivó correctamente, False en caso contrario
        """
        session = self.get_session()
        try:
            cuenta = session.query(Cuenta).filter_by(id=cuenta_id).first()
            if not cuenta:
                st.error("Cuenta no encontrada")
                return False
            
            cuenta.activa = False
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al desactivar cuenta: {e}")
            return False
        finally:
            session.close()
    
    def add_gasto(self, fecha: date, cuenta: str, descripcion: str, 
                  categoria: Optional[str], tipo: str, etiqueta: Optional[str], 
                  importe: float, recurrente_id: Optional[str] = None) -> bool:
        """
        Agrega un nuevo gasto a la base de datos.
        
        Args:
            fecha (date): Fecha del gasto
            cuenta (str): Nombre de la cuenta
            descripcion (str): Descripción del gasto
            categoria (Optional[str]): Categoría del gasto (puede ser None)
            tipo (str): Tipo de gasto ('Fijo', 'Variable', 'Otro')
            etiqueta (Optional[str]): Etiqueta del gasto (puede ser None)
            importe (float): Importe del gasto
            recurrente_id (Optional[str]): ID del gasto recurrente (puede ser None)
        
        Returns:
            bool: True si se agregó correctamente, False en caso contrario
        """
        session = self.get_session()
        try:
            # Buscar o crear cuenta
            cuenta_obj = session.query(Cuenta).filter_by(nombre=cuenta).first()
            if not cuenta_obj:
                cuenta_obj = Cuenta(nombre=cuenta)
                session.add(cuenta_obj)
                session.flush()
            
            # Buscar o crear categoría
            categoria_obj = None
            if categoria:
                categoria_obj = session.query(Categoria).filter_by(nombre=categoria).first()
                if not categoria_obj:
                    categoria_obj = Categoria(nombre=categoria)
                    session.add(categoria_obj)
                    session.flush()
            
            # Buscar o crear etiqueta
            etiqueta_obj = None
            if etiqueta:
                etiqueta_obj = session.query(Etiqueta).filter_by(nombre=etiqueta).first()
                if not etiqueta_obj:
                    etiqueta_obj = Etiqueta(nombre=etiqueta)
                    session.add(etiqueta_obj)
                    session.flush()
            
            # Crear el gasto
            nuevo_gasto = Gasto(
                fecha=datetime.combine(fecha, datetime.min.time()),
                cuenta_id=cuenta_obj.id,
                descripcion=descripcion,
                categoria_id=categoria_obj.id if categoria_obj else None,
                tipo=tipo,
                etiqueta_id=etiqueta_obj.id if etiqueta_obj else None,
                importe=importe,
                recurrente_id=recurrente_id
            )
            session.add(nuevo_gasto)
            # Ajustar saldo de la cuenta (los gastos restan)
            try:
                cuenta_obj.saldo_inicial = float(cuenta_obj.saldo_inicial) - float(importe)
            except Exception:
                pass
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al agregar gasto: {e}")
            return False
        finally:
            session.close()
    
    def add_ingreso(self, fecha: date, cuenta: str, descripcion: str, 
                   fuente: str, bruto: float, neto: float) -> bool:
        """
        Agrega un nuevo ingreso a la base de datos.
        
        Args:
            fecha (date): Fecha del ingreso
            cuenta (str): Nombre de la cuenta
            descripcion (str): Descripción del ingreso
            fuente (str): Fuente del ingreso
            bruto (float): Importe bruto (solo informativo)
            neto (float): Importe neto (modifica el balance)
        
        Returns:
            bool: True si se agregó correctamente, False en caso contrario
        """
        session = self.get_session()
        try:
            # Buscar o crear cuenta
            cuenta_obj = session.query(Cuenta).filter_by(nombre=cuenta).first()
            if not cuenta_obj:
                cuenta_obj = Cuenta(nombre=cuenta)
                session.add(cuenta_obj)
                session.flush()
            
            # Crear el ingreso
            nuevo_ingreso = Ingreso(
                fecha=datetime.combine(fecha, datetime.min.time()),
                cuenta_id=cuenta_obj.id,
                descripcion=descripcion,
                fuente=fuente,
                bruto=bruto,
                neto=neto
            )
            session.add(nuevo_ingreso)
            
            # Ajustar saldo de la cuenta (solo el neto y solo si no es fecha futura)
            if fecha <= date.today():
                try:
                    cuenta_obj.saldo_inicial = float(cuenta_obj.saldo_inicial) + float(neto)
                except Exception:
                    pass
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al agregar ingreso: {e}")
            return False
        finally:
            session.close()

    def delete_ingreso(self, ingreso_id: int) -> bool:
        """
        Elimina un ingreso y revierte su efecto en el saldo de la cuenta.
        Solo revierte el neto, no el bruto.
        """
        session = self.get_session()
        try:
            ingreso = session.query(Ingreso).filter_by(id=ingreso_id).first()
            if not ingreso:
                st.error("Ingreso no encontrado")
                return False
            
            # Guardar datos para deshacer
            ingreso_data = {
                'fecha': ingreso.fecha,
                'cuenta_id': ingreso.cuenta_id,
                'descripcion': ingreso.descripcion,
                'fuente': ingreso.fuente,
                'bruto': ingreso.bruto,
                'neto': ingreso.neto,
                'fecha_creacion': ingreso.fecha_creacion,
                'fecha_modificacion': ingreso.fecha_modificacion
            }
            
            # Revertir saldo en cuenta (solo el neto)
            cuenta = session.query(Cuenta).filter_by(id=ingreso.cuenta_id).first()
            if cuenta and ingreso.fecha.date() <= date.today():
                try:
                    cuenta.saldo_inicial = float(cuenta.saldo_inicial) - float(ingreso.neto)
                except Exception:
                    pass
            
            # Borrar ingreso
            session.delete(ingreso)
            session.commit()
            
            # Agregar a la pila de deshacer
            self.add_undo_action('delete_ingreso', ingreso_data)
            
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al eliminar ingreso: {e}")
            return False
        finally:
            session.close()

    def delete_gasto(self, gasto_id: int) -> bool:
        """
        Elimina un gasto y revierte su efecto en el saldo de la cuenta.
        """
        session = self.get_session()
        try:
            gasto = session.query(Gasto).filter_by(id=gasto_id).first()
            if not gasto:
                st.error("Gasto no encontrado")
                return False
            
            # Guardar datos para deshacer
            gasto_data = {
                'fecha': gasto.fecha,
                'cuenta_id': gasto.cuenta_id,
                'descripcion': gasto.descripcion,
                'categoria_id': gasto.categoria_id,
                'tipo': gasto.tipo,
                'etiqueta_id': gasto.etiqueta_id,
                'importe': gasto.importe,
                'recurrente_id': gasto.recurrente_id,
                'fecha_creacion': gasto.fecha_creacion,
                'fecha_modificacion': gasto.fecha_modificacion
            }
            
            # Revertir saldo en cuenta
            cuenta = session.query(Cuenta).filter_by(id=gasto.cuenta_id).first()
            if cuenta:
                try:
                    cuenta.saldo_inicial = float(cuenta.saldo_inicial) + float(gasto.importe)
                except Exception:
                    pass
            
            # Borrar gasto
            session.delete(gasto)
            session.commit()
            
            # Agregar a la pila de deshacer
            self.add_undo_action('delete_gasto', gasto_data)
            
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al eliminar gasto: {e}")
            return False
        finally:
            session.close()
    
    def update_ingreso(self, ingreso_id: int, fecha: date, cuenta: str, descripcion: str,
                      fuente: str, bruto: float, neto: float) -> bool:
        """
        Actualiza un ingreso existente en la base de datos.
        
        Args:
            ingreso_id (int): ID del ingreso a actualizar
            fecha (date): Nueva fecha del ingreso
            cuenta (str): Nombre de la cuenta
            descripcion (str): Nueva descripción del ingreso
            fuente (str): Nueva fuente del ingreso
            bruto (float): Nuevo importe bruto (solo informativo)
            neto (float): Nuevo importe neto (modifica el balance)
        
        Returns:
            bool: True si se actualizó correctamente, False en caso contrario
        """
        session = self.get_session()
        try:
            ingreso = session.query(Ingreso).filter_by(id=ingreso_id).first()
            if not ingreso:
                st.error("Ingreso no encontrado")
                return False
            
            # Buscar o crear cuenta
            cuenta_obj = session.query(Cuenta).filter_by(nombre=cuenta).first()
            if not cuenta_obj:
                cuenta_obj = Cuenta(nombre=cuenta)
                session.add(cuenta_obj)
                session.flush()
            
            # Revertir el saldo anterior si no era fecha futura
            if ingreso.fecha.date() <= date.today():
                try:
                    cuenta_anterior = session.query(Cuenta).filter_by(id=ingreso.cuenta_id).first()
                    if cuenta_anterior:
                        cuenta_anterior.saldo_inicial = float(cuenta_anterior.saldo_inicial) - float(ingreso.neto)
                except Exception:
                    pass
            
            # Actualizar el ingreso
            ingreso.fecha = datetime.combine(fecha, datetime.min.time())
            ingreso.cuenta_id = cuenta_obj.id
            ingreso.descripcion = descripcion
            ingreso.fuente = fuente
            ingreso.bruto = bruto
            ingreso.neto = neto
            ingreso.fecha_modificacion = datetime.now()
            
            # Aplicar el nuevo saldo si no es fecha futura
            if fecha <= date.today():
                try:
                    cuenta_obj.saldo_inicial = float(cuenta_obj.saldo_inicial) + float(neto)
                except Exception:
                    pass
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al actualizar ingreso: {e}")
            return False
        finally:
            session.close()

    def get_recurrentes_df(self) -> pd.DataFrame:
        """
        Obtiene los gastos recurrentes como DataFrame.
        
        Returns:
            pd.DataFrame: Recurrentes con nombres de cuenta y categoría
        """
        session = self.get_session()
        try:
            query = session.query(
                Recurrente.id,
                Recurrente.nombre,
                Recurrente.importe,
                Recurrente.periodicidad,
                Recurrente.dia_mes,
                Cuenta.nombre.label('Cuenta'),
                Categoria.nombre.label('Categoria'),
                Recurrente.activo
            ).outerjoin(Cuenta, Recurrente.cuenta_id == Cuenta.id)\
             .outerjoin(Categoria, Recurrente.categoria_id == Categoria.id)
            df = pd.read_sql(query.statement, session.bind)
            return df
        finally:
            session.close()

    def add_recurrente(self, nombre: str, importe: float, periodicidad: str, dia_mes: int,
                        cuenta: Optional[str], categoria: Optional[str]) -> bool:
        """
        Agrega un gasto recurrente.
        """
        session = self.get_session()
        try:
            cuenta_obj = None
            if cuenta:
                cuenta_obj = session.query(Cuenta).filter_by(nombre=cuenta).first()
                if not cuenta_obj:
                    cuenta_obj = Cuenta(nombre=cuenta)
                    session.add(cuenta_obj)
                    session.flush()
            categoria_obj = None
            if categoria:
                categoria_obj = session.query(Categoria).filter_by(nombre=categoria).first()
                if not categoria_obj:
                    categoria_obj = Categoria(nombre=categoria)
                    session.add(categoria_obj)
                    session.flush()

            nuevo = Recurrente(
                nombre=nombre,
                importe=importe,
                periodicidad=periodicidad,
                dia_mes=dia_mes,
                cuenta_id=cuenta_obj.id if cuenta_obj else None,
                categoria_id=categoria_obj.id if categoria_obj else None,
                activo=True
            )
            session.add(nuevo)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al agregar recurrente: {e}")
            return False
        finally:
            session.close()

    def toggle_recurrente_activo(self, recurrente_id: int, activo: bool) -> bool:
        """Activa o desactiva un recurrente."""
        session = self.get_session()
        try:
            rec = session.query(Recurrente).filter_by(id=recurrente_id).first()
            if not rec:
                st.error("Recurrente no encontrado")
                return False
            rec.activo = activo
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al actualizar recurrente: {e}")
            return False
        finally:
            session.close()

    def aplicar_recurrentes_mes(self, month_start: date) -> int:
        """
        Genera gastos del mes para todos los recurrentes activos si no existen ya.
        
        Returns:
            int: Número de gastos creados
        """
        session = self.get_session()
        try:
            # Rango del mes
            start_dt = pd.Timestamp(month_start.year, month_start.month, 1)
            last_day = calendar.monthrange(month_start.year, month_start.month)[1]
            end_dt = pd.Timestamp(month_start.year, month_start.month, last_day, 23, 59, 59)

            recurrentes = session.query(Recurrente).filter_by(activo=True).all()
            creados = 0
            for rec in recurrentes:
                # Evitar duplicados del mismo mes
                ya_existe = session.query(Gasto).filter(
                    Gasto.recurrente_id == str(rec.id),
                    Gasto.fecha >= start_dt,
                    Gasto.fecha <= end_dt
                ).first()
                if ya_existe:
                    continue

                # Determinar fecha del gasto (clamp al último día si es necesario)
                dia = min(rec.dia_mes or 1, last_day)
                fecha_gasto = datetime(month_start.year, month_start.month, dia)

                # Se requiere cuenta para crear el gasto
                if not rec.cuenta_id:
                    # Si no hay cuenta definida, saltar y advertir
                    # Nota: se muestra un único aviso agregado al final desde la UI
                    continue

                nuevo_gasto = Gasto(
                    fecha=fecha_gasto,
                    cuenta_id=rec.cuenta_id,
                    descripcion=rec.nombre,
                    categoria_id=rec.categoria_id,
                    tipo='Fijo',
                    etiqueta_id=None,
                    importe=rec.importe,
                    recurrente_id=str(rec.id)
                )
                session.add(nuevo_gasto)
                # Restar del saldo de la cuenta asociada
                try:
                    cuenta = session.query(Cuenta).filter_by(id=rec.cuenta_id).first()
                    if cuenta:
                        cuenta.saldo_inicial = float(cuenta.saldo_inicial) - float(rec.importe)
                except Exception:
                    pass
                creados += 1

            session.commit()
            return creados
        except Exception as e:
            session.rollback()
            st.error(f"Error al aplicar recurrentes: {e}")
            return 0
        finally:
            session.close()
    
    def compute_kpis(self, month_start: date) -> KPIMetrics:
        """
        Calcula los KPIs financieros del mes especificado.
        
        Args:
            month_start (date): Fecha de inicio del mes a analizar
        
        Returns:
            KPIMetrics: Objeto con todas las métricas calculadas
        """
        # Obtener datos del mes
        gastos_df = self.get_gastos_df(month_start)
        ingresos_df = self.get_ingresos_df(month_start)
        
        # Calcular totales básicos
        ingresos_netos = ingresos_df['neto'].sum() if not ingresos_df.empty else 0
        gastos_totales = gastos_df['importe'].sum() if not gastos_df.empty else 0
        
        # Calcular gastos por tipo
        gastos_fijos = gastos_df[gastos_df['tipo'].str.lower() == 'fijo']['importe'].sum() if not gastos_df.empty else 0
        gastos_variables = gastos_df[gastos_df['tipo'].str.lower() == 'variable']['importe'].sum() if not gastos_df.empty else 0
        
        # Obtener ahorro automático configurado (cantidad fija que se guarda al principio del mes)
        ahorro_automatico = self.config.get("Ahorro automático mensual", 500.0)
        
        # Obtener total de sobres actuales (lo que realmente tienes guardado)
        total_sobres_actual = self.get_total_sobres_actual()
        
        # El ahorro neto es la cantidad fija que guardas (ahorro automático)
        ahorro_neto = ahorro_automatico
        
        # Calcular tasa de ahorro basada en ingresos
        tasa_ahorro = (ahorro_neto / ingresos_netos) if ingresos_netos > 0 else 0
        
        # Calcular objetivos basados en la configuración
        pct_ahorro = self.config.get("% Ahorro objetivo", 0.25)
        pct_fijos = self.config.get("% Fijos (necesidades)", 0.50)
        pct_variables = self.config.get("% Variables (deseos)", 0.25)
        
        objetivo_ahorro = ingresos_netos * pct_ahorro
        objetivo_fijos = ingresos_netos * pct_fijos
        objetivo_variables = ingresos_netos * pct_variables
        
        return KPIMetrics(
            ingresos_netos=ingresos_netos,
            gastos_totales=gastos_totales,
            ahorro_neto=ahorro_neto,
            tasa_ahorro=tasa_ahorro,
            objetivo_ahorro=objetivo_ahorro,
            objetivo_fijos=objetivo_fijos,
            objetivo_variables=objetivo_variables,
            actual_fijos=gastos_fijos,
            actual_variables=gastos_variables
        )
    
    def get_budget_blocks(self, kpis: KPIMetrics) -> List[BudgetBlock]:
        """
        Obtiene los bloques de presupuesto leyendo directamente de la base de datos.
        
        Args:
            kpis (KPIMetrics): Métricas calculadas del mes
        
        Returns:
            List[BudgetBlock]: Lista de bloques de presupuesto
        """
        # Obtener valores directamente de la base de datos
        ahorro_automatico = self.config.get("Ahorro automático mensual", 0.0)
        objetivo_fijos = self.config.get("Objetivo gastos fijos", 0.0)
        objetivo_variables = self.config.get("Objetivo gastos variables", 0.0)
        
        # Obtener total de sobres activos
        total_sobres_objetivo = self.get_total_sobres_objetivo()
        total_sobres_actual = self.get_total_sobres_actual()
        
        # Calcular objetivo total de ahorro (automático + sobres)
        objetivo_total_ahorro = ahorro_automatico + total_sobres_objetivo
        actual_total_ahorro = ahorro_automatico + total_sobres_actual
        

        
        return [
            BudgetBlock("Ahorro automático", objetivo_total_ahorro, actual_total_ahorro, 
                       actual_total_ahorro - objetivo_total_ahorro),  # actual - objetivo
            BudgetBlock("Fijos", objetivo_fijos, kpis.actual_fijos,
                       objetivo_fijos - kpis.actual_fijos),  # objetivo - actual
            BudgetBlock("Variables", objetivo_variables, kpis.actual_variables,
                       objetivo_variables - kpis.actual_variables)  # objetivo - actual
        ]
    
    def migrate_from_excel(self, excel_path: str) -> bool:
        """
        Migra datos desde un archivo Excel a la base de datos.
        
        Args:
            excel_path (str): Ruta al archivo Excel a migrar
        
        Returns:
            bool: True si la migración fue exitosa, False en caso contrario
        """
        try:
            self.db_manager.migrate_from_excel(excel_path)
            st.success("✅ Migración completada exitosamente")
            return True
        except Exception as e:
            st.error(f"❌ Error en la migración: {e}")
            return False

    def get_gasto_classification_rules(self) -> dict:
        """Obtener reglas de clasificación aprendidas para gastos"""
        session = self.get_session()
        try:
            # Buscar configuración de reglas de clasificación
            rules_config = get_config_value(session, "gasto_classification_rules", "{}")
            if isinstance(rules_config, str):
                return json.loads(rules_config)
            return rules_config
        finally:
            session.close()

    def save_gasto_classification_rules(self, rules: dict) -> bool:
        """Guardar reglas de clasificación aprendidas"""
        session = self.get_session()
        try:
            set_config_value(session, "gasto_classification_rules", json.dumps(rules), "string")
            return True
        except Exception as e:
            st.error(f"Error al guardar reglas: {e}")
            return False
        finally:
            session.close()

    def classify_gasto_description(self, description: str) -> dict:
        """Clasificar un gasto basado en descripción usando reglas aprendidas"""
        rules = self.get_gasto_classification_rules()
        
        # Normalizar descripción para comparación
        normalized_desc = description.lower().strip()
        
        # Buscar coincidencias exactas o parciales
        for pattern, classification in rules.items():
            if pattern.lower() in normalized_desc or normalized_desc in pattern.lower():
                return classification
        return None

    def learn_gasto_classification(self, description: str, classification: dict):
        """Aprender nueva clasificación para futuras importaciones"""
        rules = self.get_gasto_classification_rules()
        
        # Normalizar descripción para usar como clave
        normalized_desc = description.lower().strip()
        
        # Guardar la clasificación
        rules[normalized_desc] = classification
        
        # También guardar variaciones comunes
        words = normalized_desc.split()
        if len(words) > 2:
            # Usar palabras clave principales
            key_words = ' '.join(words[:2])
            rules[key_words] = classification
        
        self.save_gasto_classification_rules(rules)

    def import_revolut_csv(self, csv_file, cuenta_nombre: str) -> dict:
        """
        Importar gastos desde CSV de Revolut con clasificación inteligente
        
        Returns:
            dict: Estadísticas de importación
        """
        try:
            # Leer CSV
            df = pd.read_csv(csv_file)
            
            # Verificar columnas requeridas para Revolut
            required_columns = ['Type', 'Product', 'Started Date', 'Completed Date', 'Description', 'Amount', 'Fee', 'Currency', 'State', 'Balance']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(f"Columnas faltantes: {missing_columns}")
            
            # Filtrar solo transacciones completadas y gastos (Amount negativo)
            df = df[
                (df['State'] == 'COMPLETED') & 
                (df['Amount'] < 0) & 
                (df['Currency'] == 'EUR')  # Solo EUR por ahora
            ].copy()
            
            if df.empty:
                return {
                    'total_transactions': 0,
                    'imported': 0,
                    'skipped': 0,
                    'errors': 0,
                    'new_classifications': 0
                }
            
            # Convertir fechas
            df['Completed Date'] = pd.to_datetime(df['Completed Date'])
            
            # Cargar gastos existentes una sola vez para evitar duplicados
            existing_gastos = self.get_gastos_df()
            
            # Crear índice de duplicados para búsqueda O(1)
            existing_keys = set()
            if not existing_gastos.empty:
                for _, gasto in existing_gastos.iterrows():
                    key = (
                        gasto['descripcion'],
                        gasto['importe'],
                        pd.to_datetime(gasto['fecha']).date()
                    )
                    existing_keys.add(key)
            
            # Procesar cada transacción
            imported = 0
            skipped = 0
            errors = 0
            new_classifications = 0
            
            for _, row in df.iterrows():
                try:
                    description = str(row['Description']).strip()
                    amount = abs(float(row['Amount']))  # Convertir a positivo
                    fecha = row['Completed Date'].date()
                    
                    # Verificar duplicados usando el índice en memoria (O(1))
                    duplicate_key = (description, amount, fecha)
                    if duplicate_key in existing_keys:
                        skipped += 1
                        continue
                    
                    # Intentar clasificar automáticamente
                    classification = self.classify_gasto_description(description)
                    
                    if classification:
                        # Usar clasificación aprendida
                        tipo = classification.get('tipo', 'Variable')
                        categoria = classification.get('categoria')
                        etiqueta = classification.get('etiqueta')
                        
                        # Crear gasto
                        if self.add_gasto(
                            fecha=fecha,
                            cuenta=cuenta_nombre,
                            descripcion=description,
                            categoria=categoria,
                            tipo=tipo,
                            etiqueta=etiqueta,
                            importe=amount
                        ):
                            imported += 1
                        else:
                            errors += 1
                    else:
                        # Necesita clasificación manual - devolver para procesar en UI
                        return {
                            'needs_classification': True,
                            'pending_transactions': df.to_dict('records'),
                            'total_transactions': len(df),
                            'imported': imported,
                            'skipped': skipped,
                            'errors': errors
                        }
                        
                except Exception as e:
                    errors += 1
                    continue
            
            return {
                'total_transactions': len(df),
                'imported': imported,
                'skipped': skipped,
                'errors': errors,
                'new_classifications': new_classifications
            }
            
        except Exception as e:
            st.error(f"Error al procesar CSV: {e}")
            return {
                'error': str(e),
                'total_transactions': 0,
                'imported': 0,
                'skipped': 0,
                'errors': 0
            }

    # =============================================================================
    # NUEVAS FUNCIONALIDADES
    # =============================================================================

    def get_temporal_data(self, months_back: int = 12) -> List[TemporalData]:
        """
        Obtiene datos temporales para análisis de tendencias.
        
        Args:
            months_back (int): Número de meses hacia atrás a analizar
            
        Returns:
            List[TemporalData]: Lista de datos temporales
        """
        temporal_data = []
        current_date = date.today()
        
        for i in range(months_back):
            # Calcular fecha del mes de manera más precisa
            if i == 0:
                month_start = current_date.replace(day=1)
            else:
                # Restar meses de manera más precisa
                year = current_date.year
                month = current_date.month - i
                while month <= 0:
                    year -= 1
                    month += 12
                month_start = date(year, month, 1)
            
            # Obtener datos del mes
            gastos_df = self.get_gastos_df(month_start)
            ingresos_df = self.get_ingresos_df(month_start)
            
            ingresos = ingresos_df['neto'].sum() if not ingresos_df.empty else 0
            gastos = gastos_df['importe'].sum() if not gastos_df.empty else 0
            ahorro = ingresos - gastos
            
            temporal_data.append(TemporalData(
                fecha=month_start.strftime("%Y-%m"),
                ingresos=ingresos,
                gastos=gastos,
                ahorro=ahorro
            ))
        
        return list(reversed(temporal_data))  # Ordenar cronológicamente



    def get_sobres_df(self) -> pd.DataFrame:
        """
        Obtiene los sobres como DataFrame.
        
        Returns:
            pd.DataFrame: DataFrame con los sobres
        """
        session = self.get_session()
        try:
            query = session.query(
                Sobre.id,
                Sobre.nombre,
                Sobre.descripcion,
                Sobre.importe_objetivo,
                Sobre.importe_actual,
                Sobre.permite_rollover,
                Sobre.cuenta_id,
                Sobre.activo,
                Cuenta.nombre.label('cuenta_nombre')
            ).outerjoin(Cuenta, Sobre.cuenta_id == Cuenta.id)\
             .filter(Sobre.activo == True)
            
            df = pd.read_sql(query.statement, session.bind)
            
            # Manejar caso donde cuenta_nombre puede ser None
            if 'cuenta_nombre' in df.columns:
                df['cuenta_nombre'] = df['cuenta_nombre'].fillna("Sin cuenta")
            else:
                df['cuenta_nombre'] = "Sin cuenta"
            
            return df
        finally:
            session.close()

    def add_sobre(self, nombre: str, descripcion: str, importe_objetivo: float, 
                 permite_rollover: bool = True, cuenta_id: int = None) -> bool:
        """
        Agrega un nuevo sobre.
        
        Args:
            nombre (str): Nombre del sobre
            descripcion (str): Descripción del sobre
            importe_objetivo (float): Importe objetivo mensual
            permite_rollover (bool): Si permite arrastrar saldo
            cuenta_id (int): ID de la cuenta asociada (opcional)
            
        Returns:
            bool: True si se agregó correctamente
        """
        session = self.get_session()
        try:
            nuevo_sobre = Sobre(
                nombre=nombre,
                descripcion=descripcion,
                importe_objetivo=importe_objetivo,
                importe_actual=0.0,
                permite_rollover=permite_rollover,
                cuenta_id=cuenta_id,
                activo=True
            )
            session.add(nuevo_sobre)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al agregar sobre: {e}")
            return False
        finally:
            session.close()

    def update_sobre_importe(self, sobre_id: int, nuevo_importe: float) -> bool:
        """
        Actualiza el importe actual de un sobre.
        
        Args:
            sobre_id (int): ID del sobre
            nuevo_importe (float): Nuevo importe actual
            
        Returns:
            bool: True si se actualizó correctamente
        """
        session = self.get_session()
        try:
            sobre = session.query(Sobre).filter_by(id=sobre_id).first()
            if not sobre:
                st.error("Sobre no encontrado")
                return False
            
            sobre.importe_actual = nuevo_importe
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al actualizar sobre: {e}")
            return False
        finally:
            session.close()

    def delete_sobre(self, sobre_id: int) -> bool:
        """
        Elimina un sobre (lo marca como inactivo).
        
        Args:
            sobre_id (int): ID del sobre a eliminar
            
        Returns:
            bool: True si se eliminó correctamente
        """
        session = self.get_session()
        try:
            sobre = session.query(Sobre).filter_by(id=sobre_id).first()
            if not sobre:
                st.error("Sobre no encontrado")
                return False
            
            sobre.activo = False
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al eliminar sobre: {e}")
            return False
        finally:
            session.close()

    def toggle_sobre_rollover(self, sobre_id: int) -> bool:
        """
        Activa o desactiva el rollover de un sobre.
        
        Args:
            sobre_id (int): ID del sobre
            
        Returns:
            bool: True si se actualizó correctamente
        """
        session = self.get_session()
        try:
            sobre = session.query(Sobre).filter_by(id=sobre_id).first()
            if not sobre:
                st.error("Sobre no encontrado")
                return False
            
            sobre.permite_rollover = not sobre.permite_rollover
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al actualizar rollover: {e}")
            return False
        finally:
            session.close()

    def get_total_sobres_objetivo(self) -> float:
        """
        Obtiene el total de importes objetivo de todos los sobres activos.
        
        Returns:
            float: Total de importes objetivo
        """
        session = self.get_session()
        try:
            result = session.query(Sobre.importe_objetivo).filter(Sobre.activo == True).all()
            return sum(row[0] for row in result) if result else 0.0
        finally:
            session.close()

    def get_total_sobres_actual(self) -> float:
        """
        Obtiene el total de importes actuales de todos los sobres activos.
        
        Returns:
            float: Total de importes actuales
        """
        session = self.get_session()
        try:
            result = session.query(Sobre.importe_actual).filter(Sobre.activo == True).all()
            return sum(row[0] for row in result) if result else 0.0
        finally:
            session.close()

    def get_objetivo_fijos_configurado(self) -> float:
        """
        Obtiene el objetivo de gastos fijos configurado.
        
        Returns:
            float: Objetivo de gastos fijos
        """
        return self.config.get("Objetivo gastos fijos", 0.0)

    def get_objetivo_variables_configurado(self) -> float:
        """
        Obtiene el objetivo de gastos variables configurado.
        
        Returns:
            float: Objetivo de gastos variables
        """
        return self.config.get("Objetivo gastos variables", 0.0)

    def save_objetivos_presupuesto(self, objetivo_fijos: float, objetivo_variables: float) -> bool:
        """
        Guarda los objetivos de presupuesto en la configuración.
        
        Args:
            objetivo_fijos (float): Objetivo de gastos fijos
            objetivo_variables (float): Objetivo de gastos variables
            
        Returns:
            bool: True si se guardó correctamente
        """
        session = self.get_session()
        try:
            set_config_value(session, "Objetivo gastos fijos", objetivo_fijos, "float")
            set_config_value(session, "Objetivo gastos variables", objetivo_variables, "float")
            session.commit()
            
            # Actualizar cache de configuración
            self._config = None
            
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al guardar objetivos: {e}")
            return False
        finally:
            session.close()

    def get_cuentas_saldo_real_df(self) -> pd.DataFrame:
        """
        Obtiene las cuentas con saldo real (descontando sobres).
        
        Returns:
            pd.DataFrame: DataFrame con las cuentas y sus saldos reales
        """
        cuentas_df = self.get_cuentas_df()
        if cuentas_df.empty:
            return cuentas_df
        
        # Obtener sobres activos
        sobres_df = self.get_sobres_df()
        
        # Crear una copia del DataFrame
        cuentas_real_df = cuentas_df.copy()
        cuentas_real_df['saldo_real'] = cuentas_real_df['saldo_inicial'].copy()
        
        # Descontar sobres de sus cuentas específicas
        for _, sobre in sobres_df.iterrows():
            if pd.notna(sobre['cuenta_id']) and sobre['cuenta_id'] is not None:
                # Descontar de la cuenta específica
                cuenta_mask = cuentas_real_df['id'] == sobre['cuenta_id']
                if cuenta_mask.any():
                    cuentas_real_df.loc[cuenta_mask, 'saldo_real'] -= sobre['importe_actual']
        
        # Descontar sobres sin cuenta específica proporcionalmente
        sobres_sin_cuenta = sobres_df[sobres_df['cuenta_id'].isna() | (sobres_df['cuenta_id'] == None)]
        if not sobres_sin_cuenta.empty:
            total_sobres_sin_cuenta = sobres_sin_cuenta['importe_actual'].sum()
            if total_sobres_sin_cuenta > 0:
                total_cuentas = cuentas_real_df['saldo_real'].sum()
                if total_cuentas > 0:
                    # Descontar proporcionalmente
                    factor = (total_cuentas - total_sobres_sin_cuenta) / total_cuentas
                    if factor > 0:
                        cuentas_real_df['saldo_real'] *= factor
                    else:
                        cuentas_real_df['saldo_real'] = 0.0
        
        return cuentas_real_df
    
    def get_cuentas_saldo_actual_df(self) -> pd.DataFrame:
        """
        Obtiene las cuentas con saldo actual considerando solo ingresos hasta la fecha actual.
        Los ingresos con fecha futura no afectan el saldo actual.
        
        Returns:
            pd.DataFrame: DataFrame con las cuentas y sus saldos actuales
        """
        cuentas_df = self.get_cuentas_df()
        if cuentas_df.empty:
            return cuentas_df
        
        # Obtener ingresos hasta la fecha actual
        session = self.get_session()
        try:
            # Calcular ingresos netos hasta hoy por cuenta
            ingresos_hasta_hoy = session.query(
                Ingreso.cuenta_id,
                func.sum(Ingreso.neto).label('ingresos_netos')
            ).filter(Ingreso.fecha <= datetime.now()).group_by(Ingreso.cuenta_id).all()
            
            # Crear diccionario de ingresos por cuenta
            ingresos_por_cuenta = {ingreso.cuenta_id: ingreso.ingresos_netos for ingreso in ingresos_hasta_hoy}
            
            # Calcular gastos hasta hoy por cuenta
            gastos_hasta_hoy = session.query(
                Gasto.cuenta_id,
                func.sum(Gasto.importe).label('gastos_totales')
            ).filter(Gasto.fecha <= datetime.now()).group_by(Gasto.cuenta_id).all()
            
            # Crear diccionario de gastos por cuenta
            gastos_por_cuenta = {gasto.cuenta_id: gasto.gastos_totales for gasto in gastos_hasta_hoy}
            
            # Calcular transferencias hasta hoy
            transferencias_origen = session.query(
                Transferencia.cuenta_origen_id,
                func.sum(Transferencia.importe).label('transferencias_salida')
            ).filter(Transferencia.fecha <= datetime.now()).group_by(Transferencia.cuenta_origen_id).all()
            
            transferencias_destino = session.query(
                Transferencia.cuenta_destino_id,
                func.sum(Transferencia.importe).label('transferencias_entrada')
            ).filter(Transferencia.fecha <= datetime.now()).group_by(Transferencia.cuenta_destino_id).all()
            
            # Crear diccionarios de transferencias
            transferencias_salida = {t.cuenta_origen_id: t.transferencias_salida for t in transferencias_origen}
            transferencias_entrada = {t.cuenta_destino_id: t.transferencias_entrada for t in transferencias_destino}
            
        finally:
            session.close()
        
        # Crear una copia del DataFrame
        cuentas_actual_df = cuentas_df.copy()
        cuentas_actual_df['saldo_actual'] = cuentas_actual_df['saldo_inicial'].copy()
        
        # Aplicar movimientos hasta la fecha actual
        for _, cuenta in cuentas_actual_df.iterrows():
            cuenta_id = cuenta['id']
            
            # Sumar ingresos netos hasta hoy
            if cuenta_id in ingresos_por_cuenta:
                cuentas_actual_df.loc[cuentas_actual_df['id'] == cuenta_id, 'saldo_actual'] += ingresos_por_cuenta[cuenta_id]
            
            # Restar gastos hasta hoy
            if cuenta_id in gastos_por_cuenta:
                cuentas_actual_df.loc[cuentas_actual_df['id'] == cuenta_id, 'saldo_actual'] -= gastos_por_cuenta[cuenta_id]
            
            # Restar transferencias de salida hasta hoy
            if cuenta_id in transferencias_salida:
                cuentas_actual_df.loc[cuentas_actual_df['id'] == cuenta_id, 'saldo_actual'] -= transferencias_salida[cuenta_id]
            
            # Sumar transferencias de entrada hasta hoy
            if cuenta_id in transferencias_entrada:
                cuentas_actual_df.loc[cuentas_actual_df['id'] == cuenta_id, 'saldo_actual'] += transferencias_entrada[cuenta_id]
        
        return cuentas_actual_df

    def get_transferencias_df(self, month_start: Optional[date] = None) -> pd.DataFrame:
        """
        Obtiene las transferencias como DataFrame.
        
        Args:
            month_start (Optional[date]): Fecha de inicio del mes a filtrar
            
        Returns:
            pd.DataFrame: DataFrame con las transferencias
        """
        session = self.get_session()
        try:
            query = session.query(
                Transferencia.id,
                Transferencia.fecha,
                Cuenta.nombre.label('Cuenta Origen'),
                Transferencia.cuenta_destino_id,
                Transferencia.importe,
                Transferencia.descripcion
            ).join(Cuenta, Transferencia.cuenta_origen_id == Cuenta.id)
            
            # Filtrar por mes si se especifica
            if month_start:
                start_dt = pd.Timestamp(month_start.year, month_start.month, 1)
                last_day = calendar.monthrange(month_start.year, month_start.month)[1]
                end_dt = pd.Timestamp(month_start.year, month_start.month, last_day, 23, 59, 59)
                query = query.filter(Transferencia.fecha >= start_dt, Transferencia.fecha <= end_dt)
            
            df = pd.read_sql(query.statement, session.bind)
            
            # Añadir nombre de cuenta destino
            if not df.empty:
                cuentas_dict = {c.id: c.nombre for c in session.query(Cuenta).all()}
                df['Cuenta Destino'] = df['cuenta_destino_id'].map(cuentas_dict)
                df = df.drop('cuenta_destino_id', axis=1)
            
            return df
        finally:
            session.close()

    def add_transferencia(self, fecha: date, cuenta_origen: str, cuenta_destino: str, 
                         importe: float, descripcion: str = "") -> bool:
        """
        Agrega una nueva transferencia.
        
        Args:
            fecha (date): Fecha de la transferencia
            cuenta_origen (str): Nombre de la cuenta origen
            cuenta_destino (str): Nombre de la cuenta destino
            importe (float): Importe de la transferencia
            descripcion (str): Descripción de la transferencia
            
        Returns:
            bool: True si se agregó correctamente
        """
        session = self.get_session()
        try:
            # Buscar cuentas
            cuenta_origen_obj = session.query(Cuenta).filter_by(nombre=cuenta_origen).first()
            cuenta_destino_obj = session.query(Cuenta).filter_by(nombre=cuenta_destino).first()
            
            if not cuenta_origen_obj or not cuenta_destino_obj:
                st.error("Una o ambas cuentas no existen")
                return False
            
            # Crear transferencia
            nueva_transferencia = Transferencia(
                fecha=datetime.combine(fecha, datetime.min.time()),
                cuenta_origen_id=cuenta_origen_obj.id,
                cuenta_destino_id=cuenta_destino_obj.id,
                importe=importe,
                descripcion=descripcion
            )
            session.add(nueva_transferencia)
            
            # Actualizar saldos de las cuentas
            cuenta_origen_obj.saldo_inicial = float(cuenta_origen_obj.saldo_inicial) - importe
            cuenta_destino_obj.saldo_inicial = float(cuenta_destino_obj.saldo_inicial) + importe
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al agregar transferencia: {e}")
            return False
        finally:
            session.close()

    def export_data_to_csv(self, data: pd.DataFrame, filename: str) -> str:
        """
        Exporta datos a CSV y retorna la ruta del archivo.
        
        Args:
            data (pd.DataFrame): Datos a exportar
            filename (str): Nombre del archivo
            
        Returns:
            str: Ruta del archivo CSV generado
        """
        csv_path = f"exports/{filename}.csv"
        Path("exports").mkdir(exist_ok=True)
        data.to_csv(csv_path, index=False, encoding='utf-8')
        return csv_path

    def export_data_to_excel(self, data_dict: Dict[str, pd.DataFrame], filename: str) -> str:
        """
        Exporta múltiples DataFrames a Excel.
        
        Args:
            data_dict (Dict[str, pd.DataFrame]): Diccionario con nombre_hoja: DataFrame
            filename (str): Nombre del archivo
            
        Returns:
            str: Ruta del archivo Excel generado
        """
        excel_path = f"exports/{filename}.xlsx"
        Path("exports").mkdir(exist_ok=True)
        
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            for sheet_name, df in data_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        return excel_path

    def add_undo_action(self, action_type: str, data: Dict[str, Any]):
        """
        Agrega una acción a la pila de deshacer.
        
        Args:
            action_type (str): Tipo de acción
            data (Dict[str, Any]): Datos para restaurar
        """
        undo_action = UndoAction(
            action_type=action_type,
            data=data,
            timestamp=datetime.now()
        )
        self.undo_stack.append(undo_action)
        
        # Mantener solo las últimas 10 acciones
        if len(self.undo_stack) > 10:
            self.undo_stack.pop(0)

    def undo_last_action(self) -> bool:
        """
        Deshace la última acción.
        
        Returns:
            bool: True si se deshizo correctamente
        """
        if not self.undo_stack:
            return False
        
        last_action = self.undo_stack.pop()
        session = self.get_session()
        
        try:
            if last_action.action_type == 'delete_gasto':
                # Restaurar gasto
                gasto_data = last_action.data
                nuevo_gasto = Gasto(**gasto_data)
                session.add(nuevo_gasto)
                
                # Restaurar saldo de cuenta
                cuenta = session.query(Cuenta).filter_by(id=gasto_data['cuenta_id']).first()
                if cuenta:
                    cuenta.saldo_inicial = float(cuenta.saldo_inicial) - float(gasto_data['importe'])
                
                session.commit()
                return True
                
            elif last_action.action_type == 'delete_ingreso':
                # Restaurar ingreso
                ingreso_data = last_action.data
                nuevo_ingreso = Ingreso(**ingreso_data)
                session.add(nuevo_ingreso)
                
                # Restaurar saldo de cuenta
                cuenta = session.query(Cuenta).filter_by(id=ingreso_data['cuenta_id']).first()
                if cuenta:
                    cuenta.saldo_inicial = float(cuenta.saldo_inicial) + float(ingreso_data['neto'])
                
                session.commit()
                return True
            
            return False
            
        except Exception as e:
            session.rollback()
            st.error(f"Error al deshacer acción: {e}")
            return False
        finally:
            session.close()

    def validate_budget_percentages(self, p_ahorro: float, p_fijos: float, p_variables: float) -> Tuple[bool, str]:
        """
        Valida que los porcentajes del presupuesto sumen 100%.
        
        Args:
            p_ahorro (float): Porcentaje de ahorro
            p_fijos (float): Porcentaje de gastos fijos
            p_variables (float): Porcentaje de gastos variables
            
        Returns:
            Tuple[bool, str]: (es_válido, mensaje)
        """
        total = p_ahorro + p_fijos + p_variables
        tolerance = 0.01  # 1% de tolerancia
        
        if abs(total - 1.0) <= tolerance:
            return True, "✅ Porcentajes válidos"
        elif total < 1.0:
            return False, f"⚠️ Los porcentajes suman {total*100:.1f}%. Falta {(1.0-total)*100:.1f}%"
        else:
            return False, f"⚠️ Los porcentajes suman {total*100:.1f}%. Excede {(total-1.0)*100:.1f}%"

    def auto_correct_budget(self, p_ahorro: float, p_fijos: float, p_variables: float) -> Tuple[float, float, float]:
        """
        Auto-corrige los porcentajes del presupuesto para que sumen 100%.
        
        Args:
            p_ahorro (float): Porcentaje de ahorro
            p_fijos (float): Porcentaje de gastos fijos
            p_variables (float): Porcentaje de gastos variables
            
        Returns:
            Tuple[float, float, float]: Porcentajes corregidos
        """
        total = p_ahorro + p_fijos + p_variables
        
        if total == 0:
            # Si todos son 0, usar valores por defecto
            return 0.25, 0.50, 0.25
        
        # Normalizar proporcionalmente
        factor = 1.0 / total
        return p_ahorro * factor, p_fijos * factor, p_variables * factor

    def update_sobre(self, sobre_id: int, nombre: str = None, descripcion: str = None, 
                    importe_objetivo: float = None, importe_actual: float = None,
                    permite_rollover: bool = None, cuenta_id: int = None) -> bool:
        """
        Actualiza un sobre con los campos proporcionados.
        
        Args:
            sobre_id (int): ID del sobre a actualizar
            nombre (str): Nuevo nombre (opcional)
            descripcion (str): Nueva descripción (opcional)
            importe_objetivo (float): Nuevo importe objetivo (opcional)
            importe_actual (float): Nuevo importe actual (opcional)
            permite_rollover (bool): Nuevo valor de rollover (opcional)
            cuenta_id (int): Nueva cuenta asociada (opcional)
            
        Returns:
            bool: True si se actualizó correctamente
        """
        session = self.get_session()
        try:
            sobre = session.query(Sobre).filter_by(id=sobre_id).first()
            if not sobre:
                st.error("Sobre no encontrado")
                return False
            
            if nombre is not None:
                sobre.nombre = nombre
            if descripcion is not None:
                sobre.descripcion = descripcion
            if importe_objetivo is not None:
                sobre.importe_objetivo = importe_objetivo
            if importe_actual is not None:
                sobre.importe_actual = importe_actual
            if permite_rollover is not None:
                sobre.permite_rollover = permite_rollover
            if cuenta_id is not None:
                sobre.cuenta_id = cuenta_id
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al actualizar sobre: {e}")
            return False
        finally:
            session.close()

# =============================================================================
# INTERFAZ DE USUARIO
# =============================================================================

def render_sidebar(app: FinanzasApp) -> date:
    """
    Renderiza la barra lateral con controles de configuración.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
    
    Returns:
        date: Mes seleccionado por el usuario
    """
    st.sidebar.subheader("⚙️ Configuración")
    
    # Migración desde Excel
    with st.sidebar.expander("🔄 Migrar desde Excel"):
        excel_file = st.file_uploader("Seleccionar Excel", type=['xlsx'])
        if excel_file and st.button("Migrar datos"):
            with open("temp_excel.xlsx", "wb") as f:
                f.write(excel_file.getvalue())
            app.migrate_from_excel("temp_excel.xlsx")
            Path("temp_excel.xlsx").unlink(missing_ok=True)
    
    # Selector de mes
    config = app.config
    default_month = config.get("Mes objetivo", date.today())
    sel_month = st.sidebar.date_input("📅 Mes objetivo", value=default_month)
    
    return sel_month

def render_dashboard(app: FinanzasApp, sel_month: date):
    """
    Renderiza el panel principal con métricas y gráficos.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
        sel_month (date): Mes seleccionado para el análisis
    """
    st.header("📊 Panel de Control")
    
    # Calcular KPIs
    kpis = app.compute_kpis(sel_month)
    
    # Obtener información de cuentas
    cuentas_df = app.get_cuentas_df()
    total_cuentas = cuentas_df['saldo_inicial'].sum() if not cuentas_df.empty else 0
    
    # Obtener saldo actual (considerando solo ingresos hasta la fecha actual)
    cuentas_actual_df = app.get_cuentas_saldo_actual_df()
    total_cuentas_actual = cuentas_actual_df['saldo_actual'].sum() if not cuentas_actual_df.empty else 0
    
    # Obtener saldo real descontando sobres
    cuentas_real_df = app.get_cuentas_saldo_real_df()
    total_cuentas_real = cuentas_real_df['saldo_real'].sum() if not cuentas_real_df.empty else 0
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("💰 Ingresos netos", f"€ {kpis.ingresos_netos:,.2f}")
    with col2:
        st.metric("💸 Gastos totales", f"€ {kpis.gastos_totales:,.2f}")
    with col3:
        st.metric("💎 Ahorro automático", f"€ {kpis.ahorro_neto:,.2f}")
    with col4:
        st.metric("📈 Tasa de ahorro", f"{kpis.tasa_ahorro*100:.1f}%")
    with col5:
        st.metric("🏦 Saldo disponible", f"€ {total_cuentas_actual:,.2f}")
    
    # Información adicional sobre sobres
    total_sobres_actual = app.get_total_sobres_actual()
    ahorro_automatico = app.config.get("Ahorro automático mensual", 500.0)
    total_sobres_objetivo = app.get_total_sobres_objetivo()
    ahorro_total_actual = ahorro_automatico + total_sobres_actual
    ahorro_total_objetivo = ahorro_automatico + total_sobres_objetivo
    
    if total_sobres_actual > 0 or ahorro_total_actual > 0:
        st.info(f"💡 **Ahorro automático**: € {ahorro_total_actual:,.2f} (Ahorro fijo: € {ahorro_automatico:,.2f} + Sobres actual: € {total_sobres_actual:,.2f}) - Objetivo: € {ahorro_total_objetivo:,.2f} | Saldo total: € {total_cuentas:,.2f} | Saldo disponible: € {total_cuentas_actual:,.2f}")
    
    # Resumen de cuentas
    if not cuentas_df.empty:
        st.subheader("🏦 Resumen de cuentas")
        col1, col2 = st.columns(2)
        
        with col1:
            # Tabla de cuentas con saldo actual
            display_df = cuentas_actual_df[['nombre', 'saldo_inicial', 'saldo_actual']].copy()
            display_df.columns = ['Cuenta', 'Saldo Total', 'Saldo Disponible']
            display_df['Saldo Total'] = display_df['Saldo Total'].apply(lambda x: f"€ {x:,.2f}")
            display_df['Saldo Disponible'] = display_df['Saldo Disponible'].apply(lambda x: f"€ {x:,.2f}")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        with col2:
            # Gráfico circular de distribución de dinero por cuenta
            # Preparar datos para el pie chart
            chart_data = cuentas_actual_df[['nombre', 'saldo_actual']].copy()
            chart_data = chart_data[chart_data['saldo_actual'] > 0]  # Solo cuentas con saldo positivo
            
            if not chart_data.empty:
                import altair as alt
                
                # Crear el pie chart
                chart = alt.Chart(chart_data).mark_arc().encode(
                    theta=alt.Theta('saldo_actual:Q', type='quantitative'),
                    color=alt.Color('nombre:N', scale=alt.Scale(scheme='pastel1')),
                    tooltip=[
                        alt.Tooltip('nombre:N', title='Cuenta'),
                        alt.Tooltip('saldo_actual:Q', format='.2f', title='Saldo (€)')
                    ]
                ).properties(
                    height=250,
                    width='container'
                )
                
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No hay cuentas con saldo disponible para mostrar")
    
    # Presupuesto por bloques
    st.subheader("🎯 Presupuesto por bloques")
    
    # Obtener valores actuales de la configuración para mostrar en la tabla
    ahorro_automatico = app.config.get("Ahorro automático mensual", 500.0)
    objetivo_fijos = app.config.get("Objetivo gastos fijos", 0.0)
    objetivo_variables = app.config.get("Objetivo gastos variables", 0.0)
    
    # Obtener total de sobres
    total_sobres_objetivo = app.get_total_sobres_objetivo()
    total_sobres_actual = app.get_total_sobres_actual()
    
    # Calcular valores actuales
    objetivo_total_ahorro = ahorro_automatico + total_sobres_objetivo
    actual_total_ahorro = ahorro_automatico + total_sobres_actual
    
    # Crear datos para tabla editable con cálculo inmediato de desviación
    budget_data = [
        {
            'Bloque': 'Ahorro automático',
            'Objetivo (€)': objetivo_total_ahorro,
            'Actual (€)': actual_total_ahorro,
            'Desviación (€)': actual_total_ahorro - objetivo_total_ahorro  # actual - objetivo
        },
        {
            'Bloque': 'Fijos',
            'Objetivo (€)': objetivo_fijos,
            'Actual (€)': kpis.actual_fijos,
            'Desviación (€)': objetivo_fijos - kpis.actual_fijos  # objetivo - actual
        },
        {
            'Bloque': 'Variables',
            'Objetivo (€)': objetivo_variables,
            'Actual (€)': kpis.actual_variables,
            'Desviación (€)': objetivo_variables - kpis.actual_variables  # objetivo - actual
        }
    ]
    
    # Crear DataFrame con índice personalizado
    budget_df = pd.DataFrame(budget_data)
    budget_df.index = ['Ahorro automático', 'Fijos', 'Variables']
    
    # Crear tabla editable con actualización automática
    edited_budget_df = st.data_editor(
        budget_df,
        use_container_width=True,
        column_config={
            "Bloque": st.column_config.TextColumn("Bloque", disabled=True),
            "Objetivo (€)": st.column_config.NumberColumn("Objetivo (€)", min_value=0.0, step=10.0),
            "Actual (€)": st.column_config.NumberColumn("Actual (€)", disabled=True),
            "Desviación (€)": st.column_config.NumberColumn("Desviación (€)", disabled=True)
        },
        key="budget_editor"
    )
    
    # Actualización automática inmediata
    if edited_budget_df is not None:
        try:
            # Obtener valores actuales de la tabla
            ahorro_objetivo = float(edited_budget_df.loc['Ahorro automático', 'Objetivo (€)'])
            fijos_objetivo = float(edited_budget_df.loc['Fijos', 'Objetivo (€)'])
            variables_objetivo = float(edited_budget_df.loc['Variables', 'Objetivo (€)'])
            
            # Verificar si hubo cambios
            if (abs(ahorro_objetivo - objetivo_total_ahorro) > 0.01 or 
                abs(fijos_objetivo - objetivo_fijos) > 0.01 or 
                abs(variables_objetivo - objetivo_variables) > 0.01):
                
                # Guardar objetivos de fijos y variables directamente en la base de datos
                app.save_objetivos_presupuesto(fijos_objetivo, variables_objetivo)
                
                # Calcular y guardar ahorro automático (restando sobres objetivo)
                ahorro_automatico = max(0.0, ahorro_objetivo - app.get_total_sobres_objetivo())
                app.save_config({
                    **app.config,
                    "Ahorro automático mensual": ahorro_automatico
                })
                
                # Mostrar mensaje de éxito
                st.success("✅ Objetivos actualizados automáticamente")
                
                # Forzar re-ejecución para actualizar la tabla
                st.rerun()
                
        except Exception as e:
            pass  # Ignorar errores silenciosamente
    
    # Gráficos de gastos
    gastos_df = app.get_gastos_df(sel_month)
    
    if not gastos_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Gastos por categoría")
            
            # Selector de tipo de gráfico para categorías
            chart_type_cat = st.selectbox(
                "📊 Tipo de gráfico",
                ["Barras", "Circular"],
                key="chart_type_categorias"
            )
            
            cat_gastos = gastos_df.groupby('Categoria')['importe'].sum().sort_values(ascending=False)
            if not cat_gastos.empty:
                max_cat = cat_gastos.max()
                chart_data = pd.DataFrame({
                    'Categoría': cat_gastos.index,
                    'Importe': cat_gastos.values
                })
                
                import altair as alt
                
                if chart_type_cat == "Barras":
                    chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X('Categoría:N', title='Categoría'),
                        y=alt.Y('Importe:Q', title='Importe (€)', scale=alt.Scale(domain=[0, max_cat * 1.1])),
                        color=alt.value('#F7CAC9')
                    ).properties(
                        height=220,
                        width='container'
                    )
                else:  # Circular
                    chart = alt.Chart(chart_data).mark_arc().encode(
                        theta=alt.Theta('Importe:Q', type='quantitative'),
                        color=alt.Color('Categoría:N', scale=alt.Scale(scheme='pastel2')),
                        tooltip=['Categoría', alt.Tooltip('Importe:Q', format='.2f', title='Importe (€)')]
                    ).properties(
                        height=220,
                        width='container'
                    )
                
                st.altair_chart(chart, use_container_width=True)
        
        with col2:
            st.subheader("🏷️ Gastos por etiqueta")
            
            # Selector de tipo de gráfico para etiquetas
            chart_type_tag = st.selectbox(
                "📊 Tipo de gráfico",
                ["Barras", "Circular"],
                key="chart_type_etiquetas"
            )
            
            tag_gastos = gastos_df.groupby('Etiqueta')['importe'].sum().sort_values(ascending=False)
            if not tag_gastos.empty:
                max_tag = tag_gastos.max()
                chart_data = pd.DataFrame({
                    'Etiqueta': tag_gastos.index,
                    'Importe': tag_gastos.values
                })
                
                import altair as alt
                
                if chart_type_tag == "Barras":
                    chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X('Etiqueta:N', title='Etiqueta'),
                        y=alt.Y('Importe:Q', title='Importe (€)', scale=alt.Scale(domain=[0, max_tag * 1.1])),
                        color=alt.value('#B8E6B8')
                    ).properties(
                        height=220,
                        width='container'
                    )
                else:  # Circular
                    chart = alt.Chart(chart_data).mark_arc().encode(
                        theta=alt.Theta('Importe:Q', type='quantitative'),
                        color=alt.Color('Etiqueta:N', scale=alt.Scale(scheme='pastel1')),
                        tooltip=['Etiqueta', alt.Tooltip('Importe:Q', format='.2f', title='Importe (€)')]
                    ).properties(
                        height=220,
                        width='container'
                    )
                
                st.altair_chart(chart, use_container_width=True)
    else:
        st.info("📝 No hay gastos registrados para este mes")
    
    # Análisis temporal
    st.subheader("📈 Análisis Temporal")
    
    # Obtener datos temporales
    temporal_data = app.get_temporal_data(12)  # Últimos 12 meses
    
    if temporal_data and len(temporal_data) > 0:
        # Crear DataFrame para el gráfico
        chart_df = pd.DataFrame([
            {
                'Fecha': data.fecha,
                'Ingresos': data.ingresos,
                'Gastos': data.gastos,
                'Ahorro': data.ahorro
            }
            for data in temporal_data
        ])
        
        # Verificar que el DataFrame no esté vacío
        if chart_df.empty:
            st.info("📝 No hay datos suficientes para mostrar el análisis temporal")
            return
        
        # Gráfico de tendencia con ejes fijos
        import altair as alt
        
        # Calcular rangos para ejes fijos
        max_ingresos = chart_df['Ingresos'].max() if not chart_df.empty else 1000
        max_gastos = chart_df['Gastos'].max() if not chart_df.empty else 1000
        max_ahorro = chart_df['Ahorro'].max() if not chart_df.empty else 1000
        min_ahorro = chart_df['Ahorro'].min() if not chart_df.empty else -1000
        
        # Gráfico de líneas
        chart = alt.Chart(chart_df).transform_fold(
            ['Ingresos', 'Gastos', 'Ahorro'],
            as_=['Tipo', 'Importe']
        ).mark_line(point=True).encode(
            x=alt.X('Fecha:N', title='Mes'),
            y=alt.Y('Importe:Q', title='Importe (€)', 
                   scale=alt.Scale(domain=[min_ahorro * 1.1, max(max_ingresos, max_gastos) * 1.1])),
            color=alt.Color('Tipo:N', scale=alt.Scale(
                domain=['Ingresos', 'Gastos', 'Ahorro'],
                range=['#2E8B57', '#DC143C', '#4169E1']
            )),
            tooltip=[alt.Tooltip('Fecha:N', title='Mes'), 
                    alt.Tooltip('Tipo:N', title='Tipo'), 
                    alt.Tooltip('Importe:Q', format='.2f', title='Importe (€)')]
        ).properties(
            height=300,
            width='container'
        )
        
        st.altair_chart(chart, use_container_width=True)
        
        # Métricas de tendencia
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if len(temporal_data) >= 2:
                crecimiento_ingresos = ((temporal_data[-1].ingresos - temporal_data[-2].ingresos) / temporal_data[-2].ingresos * 100) if temporal_data[-2].ingresos > 0 else 0
                st.metric("📈 Crecimiento ingresos", f"{crecimiento_ingresos:+.1f}%")
        
        with col2:
            if len(temporal_data) >= 2:
                crecimiento_gastos = ((temporal_data[-1].gastos - temporal_data[-2].gastos) / temporal_data[-2].gastos * 100) if temporal_data[-2].gastos > 0 else 0
                st.metric("📉 Crecimiento gastos", f"{crecimiento_gastos:+.1f}%")
        
        with col3:
            if len(temporal_data) >= 2:
                crecimiento_ahorro = ((temporal_data[-1].ahorro - temporal_data[-2].ahorro) / abs(temporal_data[-2].ahorro) * 100) if temporal_data[-2].ahorro != 0 else 0
                st.metric("💎 Crecimiento ahorro", f"{crecimiento_ahorro:+.1f}%")

def render_gastos_tab(app: FinanzasApp, sel_month: date):
    """
    Renderiza la pestaña de gestión de gastos.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
        sel_month (date): Mes seleccionado
    """
    st.header("💸 Gestión de Gastos")
    
    # Mostrar gastos del mes
    gastos_df = app.get_gastos_df(sel_month)
    
    # Debug: Mostrar información del mes seleccionado
    st.write(f"📅 **Mes seleccionado**: {sel_month.strftime('%B %Y')}")
    
    # Botones de exportación
    if not gastos_df.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📥 Exportar CSV"):
                csv_path = app.export_data_to_csv(gastos_df, f"gastos_{sel_month.strftime('%Y_%m')}")
                with open(csv_path, 'r') as f:
                    st.download_button(
                        label="💾 Descargar CSV",
                        data=f.read(),
                        file_name=f"gastos_{sel_month.strftime('%Y_%m')}.csv",
                        mime="text/csv"
                    )
        
        with col2:
            if st.button("📊 Exportar Excel"):
                excel_path = app.export_data_to_excel(
                    {"Gastos": gastos_df}, 
                    f"gastos_{sel_month.strftime('%Y_%m')}"
                )
                with open(excel_path, 'rb') as f:
                    st.download_button(
                        label="💾 Descargar Excel",
                        data=f.read(),
                        file_name=f"gastos_{sel_month.strftime('%Y_%m')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        
        with col3:
            if st.button("↩️ Deshacer última acción"):
                if app.undo_last_action():
                    st.success("✅ Acción deshecha correctamente")
                    st.rerun()
                else:
                    st.warning("⚠️ No hay acciones para deshacer")
    
    # Opción para ver todos los gastos
    if st.checkbox("👁️ Ver todos los gastos (sin filtro de mes)"):
        all_gastos_df = app.get_gastos_df(None)  # Sin filtro de mes
        if not all_gastos_df.empty:
            st.write("📋 **Todos los gastos registrados:**")
            
            # Crear DataFrame con checkboxes para selección
            all_gastos_con_checkbox = all_gastos_df.copy()
            all_gastos_con_checkbox['Seleccionar'] = False
            
            # Usar st.data_editor para permitir interacción
            all_edited_df = st.data_editor(
                all_gastos_con_checkbox,
                use_container_width=True,
                key="all_gastos_editor",
                column_config={
                    "Seleccionar": st.column_config.CheckboxColumn(
                        "🗑️ Seleccionar",
                        help="Marca los gastos que quieres eliminar"
                    ),
                    "id": st.column_config.NumberColumn(
                        "ID",
                        help="Identificador único del gasto"
                    ),
                    "fecha": st.column_config.DatetimeColumn(
                        "📅 Fecha",
                        help="Fecha del gasto"
                    ),
                    "Cuenta": st.column_config.TextColumn(
                        "🏦 Cuenta",
                        help="Cuenta de donde se descontó"
                    ),
                    "descripcion": st.column_config.TextColumn(
                        "📝 Descripción",
                        help="Descripción del gasto"
                    ),
                    "Categoria": st.column_config.TextColumn(
                        "📂 Categoría",
                        help="Categoría del gasto"
                    ),
                    "tipo": st.column_config.SelectboxColumn(
                        "🏷️ Tipo",
                        help="Tipo de gasto",
                        options=["Variable", "Fijo", "Otro"]
                    ),
                    "Etiqueta": st.column_config.TextColumn(
                        "🏷️ Etiqueta",
                        help="Etiqueta del gasto"
                    ),
                    "importe": st.column_config.NumberColumn(
                        "💰 Importe",
                        help="Importe del gasto",
                        format="%.2f €"
                    ),
                    "recurrente_id": st.column_config.TextColumn(
                        "🔄 Recurrente",
                        help="ID del gasto recurrente si aplica"
                    )
                }
            )
            
            # Botón para eliminar gastos seleccionados (todos los gastos)
            all_gastos_seleccionados = all_edited_df[all_edited_df['Seleccionar'] == True]
            if not all_gastos_seleccionados.empty:
                st.write(f"🗑️ **Gastos seleccionados para eliminar**: {len(all_gastos_seleccionados)}")
                
                # Mostrar resumen de gastos a eliminar
                for _, gasto in all_gastos_seleccionados.iterrows():
                    st.write(f"• {gasto['descripcion']} - €{gasto['importe']:.2f} ({gasto['fecha'].date()})")
                
                if st.button("🗑️ Eliminar gastos seleccionados (todos)", type="primary", key="delete_all_gastos"):
                    eliminados = 0
                    for _, gasto in all_gastos_seleccionados.iterrows():
                        if app.delete_gasto(int(gasto['id'])):
                            eliminados += 1
                    
                    if eliminados > 0:
                        st.success(f"✅ Se eliminaron {eliminados} gastos correctamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al eliminar los gastos")
        else:
            st.warning("⚠️ No hay gastos registrados en ninguna fecha")
    
    # Mostrar gastos del mes seleccionado con opción de eliminar
    if not gastos_df.empty:
        # Crear DataFrame con checkboxes para selección
        gastos_con_checkbox = gastos_df.copy()
        gastos_con_checkbox['Seleccionar'] = False
        
        # Usar st.data_editor para permitir interacción
        edited_df = st.data_editor(
            gastos_con_checkbox,
            use_container_width=True,
            key="month_gastos_editor",
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn(
                    "🗑️ Seleccionar",
                    help="Marca los gastos que quieres eliminar"
                ),
                "id": st.column_config.NumberColumn(
                    "ID",
                    help="Identificador único del gasto"
                ),
                "fecha": st.column_config.DatetimeColumn(
                    "📅 Fecha",
                    help="Fecha del gasto"
                ),
                "Cuenta": st.column_config.TextColumn(
                    "🏦 Cuenta",
                    help="Cuenta de donde se descontó"
                ),
                "descripcion": st.column_config.TextColumn(
                    "📝 Descripción",
                    help="Descripción del gasto"
                ),
                "Categoria": st.column_config.TextColumn(
                    "📂 Categoría",
                    help="Categoría del gasto"
                ),
                "tipo": st.column_config.SelectboxColumn(
                    "🏷️ Tipo",
                    help="Tipo de gasto",
                    options=["Variable", "Fijo", "Otro"]
                ),
                "Etiqueta": st.column_config.TextColumn(
                    "🏷️ Etiqueta",
                    help="Etiqueta del gasto"
                ),
                "importe": st.column_config.NumberColumn(
                    "💰 Importe",
                    help="Importe del gasto",
                    format="%.2f €"
                ),
                "recurrente_id": st.column_config.TextColumn(
                    "🔄 Recurrente",
                    help="ID del gasto recurrente si aplica"
                )
            }
        )
        
        # Botón para eliminar gastos seleccionados
        gastos_seleccionados = edited_df[edited_df['Seleccionar'] == True]
        if not gastos_seleccionados.empty:
            st.write(f"🗑️ **Gastos seleccionados para eliminar**: {len(gastos_seleccionados)}")
            
            # Mostrar resumen de gastos a eliminar
            for _, gasto in gastos_seleccionados.iterrows():
                st.write(f"• {gasto['descripcion']} - €{gasto['importe']:.2f} ({gasto['fecha'].date()})")
            
            if st.button("🗑️ Eliminar gastos seleccionados", type="primary", key="delete_month_gastos"):
                eliminados = 0
                for _, gasto in gastos_seleccionados.iterrows():
                    if app.delete_gasto(int(gasto['id'])):
                        eliminados += 1
                
                if eliminados > 0:
                    st.success(f"✅ Se eliminaron {eliminados} gastos correctamente")
                    st.rerun()
                else:
                    st.error("❌ Error al eliminar los gastos")
    else:
        st.info("📝 No hay gastos registrados para este mes")
    
    # Importación desde CSV
    with st.expander("📁 Importar desde CSV"):
        st.subheader("🔄 Importación Inteligente")
        st.write("Sube tu archivo CSV bancario y el sistema aprenderá automáticamente cómo clasificar tus gastos.")
        
        # Obtener cuentas disponibles
        cuentas_df = app.get_cuentas_df()
        cuentas_disponibles = cuentas_df['nombre'].tolist() if not cuentas_df.empty else []
        
        if not cuentas_disponibles:
            st.warning("⚠️ Primero crea una cuenta en la pestaña '🏦 Cuentas'")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                csv_file = st.file_uploader("Seleccionar archivo CSV", type=['csv'])
            
            with col2:
                cuenta = st.selectbox("🏦 Cuenta", ["Revolut", "Caixa"])
            
            if csv_file and cuenta:
                if st.button("🚀 Procesar CSV"):
                    with st.spinner("Procesando archivo..."):
                        if cuenta == "Revolut":
                            result = app.import_revolut_csv(csv_file, cuenta)
                        elif cuenta == "Caixa":
                            st.warning("⚠️ **Caixa aún no está implementado**")
                            st.info("La importación desde Caixa estará disponible próximamente. Por ahora, puedes usar la clasificación manual en la pestaña de gastos.")
                            return
                    
                    if 'error' in result:
                        st.error(f"❌ Error: {result['error']}")
                    elif result.get('needs_classification', False):
                        # Mostrar transacciones que necesitan clasificación
                        st.session_state.pending_classifications = result['pending_transactions']
                        st.session_state.cuenta_destino = cuenta
                        st.session_state.tipo_banco = cuenta
                        st.success(f"📋 Se encontraron {len(result['pending_transactions'])} transacciones que necesitan clasificación")
                        st.rerun()
                    else:
                        st.success(f"✅ Importación completada:")
                        st.write(f"• **Importados**: {result['imported']}")
                        st.write(f"• **Omitidos** (duplicados): {result['skipped']}")
                        st.write(f"• **Errores**: {result['errors']}")
                        st.rerun()
    
    # Clasificación manual de transacciones pendientes
    if 'pending_classifications' in st.session_state and st.session_state.pending_classifications:
        st.subheader("🎯 Clasificar Transacciones")
        st.write("Clasifica las transacciones para que el sistema aprenda automáticamente en futuras importaciones.")
        
        pending = st.session_state.pending_classifications
        current_index = st.session_state.get('classification_index', 0)
        
        if current_index < len(pending):
            transaction = pending[current_index]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Descripción**: {transaction['Description']}")
                st.write(f"**Importe**: €{abs(float(transaction['Amount'])):.2f}")
                st.write(f"**Fecha**: {transaction['Completed Date']}")
                
                # Formulario de clasificación
                with st.form(f"classify_{current_index}"):
                    tipo = st.selectbox("🏷️ Tipo", ["Variable", "Fijo"], key=f"tipo_{current_index}")
                    categoria = st.text_input("📂 Categoría", key=f"cat_{current_index}")
                    etiqueta = st.text_input("🏷️ Etiqueta (opcional)", key=f"etq_{current_index}")
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.form_submit_button("💾 Clasificar y Continuar"):
                            # Aprender clasificación
                            classification = {
                                'tipo': tipo,
                                'categoria': categoria if categoria else None,
                                'etiqueta': etiqueta if etiqueta else None
                            }
                            app.learn_gasto_classification(transaction['Description'], classification)
                            
                            # Crear gasto
                            fecha = pd.to_datetime(transaction['Completed Date']).date()
                            amount = abs(float(transaction['Amount']))
                            
                            if app.add_gasto(
                                fecha=fecha,
                                cuenta=st.session_state.cuenta_destino,
                                descripcion=transaction['Description'],
                                categoria=categoria if categoria else None,
                                tipo=tipo,
                                etiqueta=etiqueta if etiqueta else None,
                                importe=amount
                            ):
                                st.session_state.classification_index = current_index + 1
                                st.success("✅ Clasificado y guardado")
                                st.rerun()
                    
                    with col_b:
                        if st.form_submit_button("⏭️ Omitir"):
                            st.session_state.classification_index = current_index + 1
                            st.rerun()
            
            with col2:
                st.write("**Progreso**:")
                progress = (current_index + 1) / len(pending)
                st.progress(progress)
                st.write(f"{current_index + 1} de {len(pending)} transacciones")
                
                # Mostrar reglas aprendidas
                rules = app.get_gasto_classification_rules()
                if rules:
                    st.write("**Reglas aprendidas**:")
                    for pattern, classification in list(rules.items())[-5:]:  # Últimas 5
                        st.write(f"• {pattern[:30]}... → {classification['tipo']}")
        
        else:
            # Todas las transacciones procesadas
            st.success("🎉 ¡Todas las transacciones han sido procesadas!")
            st.write("El sistema ha aprendido tus patrones de gasto y podrá clasificar automáticamente en futuras importaciones.")
            
            # Limpiar session state
            if 'pending_classifications' in st.session_state:
                del st.session_state.pending_classifications
            if 'classification_index' in st.session_state:
                del st.session_state.classification_index
            if 'cuenta_destino' in st.session_state:
                del st.session_state.cuenta_destino
            if 'tipo_banco' in st.session_state:
                del st.session_state.tipo_banco
            
            if st.button("🔄 Procesar más transacciones"):
                st.rerun()
    
    # Formulario para agregar gasto manual
    with st.expander("➕ Agregar nuevo gasto manual"):
        with st.form("nuevo_gasto"):
            col1, col2 = st.columns(2)
            
            with col1:
                fecha = st.date_input("📅 Fecha", value=sel_month)
                
                # Obtener cuentas disponibles
                cuentas_df = app.get_cuentas_df()
                cuentas_disponibles = cuentas_df['nombre'].tolist() if not cuentas_df.empty else []
                
                if cuentas_disponibles:
                    cuenta = st.selectbox("🏦 Cuenta", cuentas_disponibles)
                else:
                    cuenta = st.text_input("🏦 Cuenta (crear nueva)")
                
                descripcion = st.text_input("📝 Descripción")
                categoria = st.text_input("📂 Categoría")
            
            with col2:
                tipo = st.selectbox("🏷️ Tipo", ["Variable", "Fijo", "Otro"])
                etiqueta = st.text_input("🏷️ Etiqueta")
                importe = st.number_input("💰 Importe", min_value=0.0, step=0.01)
            
            if st.form_submit_button("💾 Agregar gasto"):
                if app.add_gasto(fecha, cuenta, descripcion, categoria, tipo, etiqueta, importe):
                    st.success("✅ Gasto agregado correctamente")
                    st.rerun()

def render_ingresos_tab(app: FinanzasApp, sel_month: date):
    """
    Renderiza la pestaña de gestión de ingresos.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
        sel_month (date): Mes seleccionado
    """
    st.header("💰 Gestión de Ingresos")
    
    # Mostrar ingresos del mes
    ingresos_df = app.get_ingresos_df(sel_month)
    
    # Botones de exportación y deshacer
    if not ingresos_df.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📥 Exportar CSV", key="export_ingresos_csv"):
                csv_path = app.export_data_to_csv(ingresos_df, f"ingresos_{sel_month.strftime('%Y_%m')}")
                with open(csv_path, 'r') as f:
                    st.download_button(
                        label="💾 Descargar CSV",
                        data=f.read(),
                        file_name=f"ingresos_{sel_month.strftime('%Y_%m')}.csv",
                        mime="text/csv"
                    )
        
        with col2:
            if st.button("📊 Exportar Excel", key="export_ingresos_excel"):
                excel_path = app.export_data_to_excel(
                    {"Ingresos": ingresos_df}, 
                    f"ingresos_{sel_month.strftime('%Y_%m')}"
                )
                with open(excel_path, 'rb') as f:
                    st.download_button(
                        label="💾 Descargar Excel",
                        data=f.read(),
                        file_name=f"ingresos_{sel_month.strftime('%Y_%m')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        
        with col3:
            if st.button("↩️ Deshacer última acción", key="undo_ingresos"):
                if app.undo_last_action():
                    st.success("✅ Acción deshecha correctamente")
                    st.rerun()
                else:
                    st.warning("⚠️ No hay acciones para deshacer")
    
    # Opción para ver todos los ingresos
    if st.checkbox("👁️ Ver todos los ingresos (sin filtro de mes)", key="ver_todos_ingresos"):
        all_ingresos_df = app.get_ingresos_df(None)  # Sin filtro de mes
        if not all_ingresos_df.empty:
            st.write("📋 **Todos los ingresos registrados:**")
            
            # Crear DataFrame con checkboxes para selección
            all_ingresos_con_checkbox = all_ingresos_df.copy()
            all_ingresos_con_checkbox['Seleccionar'] = False
            
            # Usar st.data_editor para permitir interacción
            all_edited_df = st.data_editor(
                all_ingresos_con_checkbox,
                use_container_width=True,
                key="all_ingresos_editor",
                column_config={
                    "Seleccionar": st.column_config.CheckboxColumn(
                        "🗑️ Seleccionar",
                        help="Marca los ingresos que quieres eliminar"
                    ),
                    "id": st.column_config.NumberColumn(
                        "ID",
                        help="Identificador único del ingreso"
                    ),
                    "fecha": st.column_config.DatetimeColumn(
                        "📅 Fecha",
                        help="Fecha del ingreso"
                    ),
                    "Cuenta": st.column_config.TextColumn(
                        "🏦 Cuenta",
                        help="Cuenta donde se ingresó el dinero"
                    ),
                    "descripcion": st.column_config.TextColumn(
                        "📝 Descripción",
                        help="Descripción del ingreso"
                    ),
                    "fuente": st.column_config.TextColumn(
                        "📤 Fuente",
                        help="Fuente del ingreso"
                    ),
                    "bruto": st.column_config.NumberColumn(
                        "💰 Bruto",
                        help="Importe bruto (solo informativo)",
                        format="%.2f €"
                    ),
                    "neto": st.column_config.NumberColumn(
                        "💎 Neto",
                        help="Importe neto (modifica el balance)",
                        format="%.2f €"
                    )
                }
            )
            
            # Botón para eliminar ingresos seleccionados (todos los ingresos)
            all_ingresos_seleccionados = all_edited_df[all_edited_df['Seleccionar'] == True]
            if not all_ingresos_seleccionados.empty:
                st.write(f"🗑️ **Ingresos seleccionados para eliminar**: {len(all_ingresos_seleccionados)}")
                
                # Mostrar resumen de ingresos a eliminar
                for _, ingreso in all_ingresos_seleccionados.iterrows():
                    st.write(f"• {ingreso['descripcion']} - €{ingreso['neto']:.2f} ({ingreso['fecha'].date()})")
                
                if st.button("🗑️ Eliminar ingresos seleccionados (todos)", type="primary", key="delete_all_ingresos"):
                    eliminados = 0
                    for _, ingreso in all_ingresos_seleccionados.iterrows():
                        if app.delete_ingreso(int(ingreso['id'])):
                            eliminados += 1
                    
                    if eliminados > 0:
                        st.success(f"✅ Se eliminaron {eliminados} ingresos correctamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al eliminar los ingresos")
        else:
            st.warning("⚠️ No hay ingresos registrados en ninguna fecha")
    
    # Mostrar ingresos del mes seleccionado con opción de eliminar
    if not ingresos_df.empty:
        # Crear DataFrame con checkboxes para selección
        ingresos_con_checkbox = ingresos_df.copy()
        ingresos_con_checkbox['Seleccionar'] = False
        
        # Usar st.data_editor para permitir interacción
        edited_df = st.data_editor(
            ingresos_con_checkbox,
            use_container_width=True,
            key="month_ingresos_editor",
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn(
                    "🗑️ Seleccionar",
                    help="Marca los ingresos que quieres eliminar"
                ),
                "id": st.column_config.NumberColumn(
                    "ID",
                    help="Identificador único del ingreso"
                ),
                "fecha": st.column_config.DatetimeColumn(
                    "📅 Fecha",
                    help="Fecha del ingreso"
                ),
                "Cuenta": st.column_config.TextColumn(
                    "🏦 Cuenta",
                    help="Cuenta donde se ingresó el dinero"
                ),
                "descripcion": st.column_config.TextColumn(
                    "📝 Descripción",
                    help="Descripción del ingreso"
                ),
                "fuente": st.column_config.TextColumn(
                    "📤 Fuente",
                    help="Fuente del ingreso"
                ),
                "bruto": st.column_config.NumberColumn(
                    "💰 Bruto",
                    help="Importe bruto (solo informativo)",
                    format="%.2f €"
                ),
                "neto": st.column_config.NumberColumn(
                    "💎 Neto",
                    help="Importe neto (modifica el balance)",
                    format="%.2f €"
                )
            }
        )
        
        # Botón para eliminar ingresos seleccionados
        ingresos_seleccionados = edited_df[edited_df['Seleccionar'] == True]
        if not ingresos_seleccionados.empty:
            st.write(f"🗑️ **Ingresos seleccionados para eliminar**: {len(ingresos_seleccionados)}")
            
            # Mostrar resumen de ingresos a eliminar
            for _, ingreso in ingresos_seleccionados.iterrows():
                st.write(f"• {ingreso['descripcion']} - €{ingreso['neto']:.2f} ({ingreso['fecha'].date()})")
            
            if st.button("🗑️ Eliminar ingresos seleccionados", type="primary", key="delete_month_ingresos"):
                eliminados = 0
                for _, ingreso in ingresos_seleccionados.iterrows():
                    if app.delete_ingreso(int(ingreso['id'])):
                        eliminados += 1
                
                if eliminados > 0:
                    st.success(f"✅ Se eliminaron {eliminados} ingresos correctamente")
                    st.rerun()
                else:
                    st.error("❌ Error al eliminar los ingresos")
    else:
        st.info("📝 No hay ingresos registrados para este mes")
    
    # Mostrar información sobre ingresos futuros
    ingresos_futuros_df = app.get_ingresos_df(None)  # Obtener todos los ingresos
    if not ingresos_futuros_df.empty:
        ingresos_futuros = ingresos_futuros_df[ingresos_futuros_df['fecha'].dt.date > date.today()]
        if not ingresos_futuros.empty:
            st.subheader("🔮 Ingresos Futuros")
            st.info(f"💰 **Total ingresos futuros**: € {ingresos_futuros['neto'].sum():,.2f}")
            st.write("📅 **Detalle de ingresos futuros:**")
            
            for _, ingreso in ingresos_futuros.iterrows():
                st.write(f"• {ingreso['fecha'].date()} - {ingreso['descripcion']} - €{ingreso['neto']:.2f} ({ingreso['Cuenta']})")
    
    # Formulario para agregar ingreso
    with st.expander("➕ Agregar nuevo ingreso"):
        with st.form("nuevo_ingreso"):
            col1, col2 = st.columns(2)
            
            with col1:
                fecha = st.date_input("📅 Fecha", value=sel_month, key="ingreso_fecha")
                
                # Obtener cuentas disponibles
                cuentas_df = app.get_cuentas_df()
                cuentas_disponibles = cuentas_df['nombre'].tolist() if not cuentas_df.empty else []
                
                if cuentas_disponibles:
                    cuenta = st.selectbox("🏦 Cuenta", cuentas_disponibles, key="ingreso_cuenta")
                else:
                    cuenta = st.text_input("🏦 Cuenta (crear nueva)", key="ingreso_cuenta")
                
                descripcion = st.text_input("📝 Descripción", key="ingreso_desc")
                fuente = st.text_input("📤 Fuente")
            
            with col2:
                bruto = st.number_input("💰 Bruto (solo informativo)", min_value=0.0, step=0.01, value=0.0, help="Importe bruto antes de impuestos y retenciones")
                # Campo neto con valor por defecto
                neto = st.number_input("💎 Neto (modifica balance)", min_value=0.0, step=0.01, value=0.0, help="Importe neto que realmente ingresa a la cuenta")
            
            # Información adicional
            st.info("💡 **Nota**: Solo el importe neto modifica el balance de la cuenta. Los ingresos con fecha futura no afectan el saldo hasta esa fecha.")
            
            if st.form_submit_button("💾 Agregar ingreso"):
                # Asegurar que los valores son float
                bruto_float = float(bruto) if bruto is not None else 0.0
                neto_float = float(neto) if neto is not None else 0.0
                
                if neto_float <= 0:
                    st.error("❌ El importe neto debe ser mayor que 0")
                elif app.add_ingreso(fecha, cuenta, descripcion, fuente, bruto_float, neto_float):
                    st.success("✅ Ingreso agregado correctamente")
                    st.rerun()

def render_recurrentes_tab(app: FinanzasApp, sel_month: date):
    """
    Renderiza la pestaña de gastos recurrentes (fijos mensuales).
    """
    st.header("🔁 Gastos recurrentes")

    # Listado de recurrentes
    rec_df = app.get_recurrentes_df()
    if not rec_df.empty:
        mostrar = rec_df.copy()
        mostrar['Estado'] = mostrar['activo'].apply(lambda x: 'Activo' if x else 'Inactivo')
        mostrar = mostrar[['nombre', 'importe', 'periodicidad', 'dia_mes', 'Cuenta', 'Categoria', 'Estado']]
        mostrar.columns = ['Nombre', 'Importe', 'Periodicidad', 'Día del mes', 'Cuenta', 'Categoría', 'Estado']
        mostrar['Importe'] = mostrar['Importe'].apply(lambda x: f"€ {x:,.2f}")
        st.dataframe(mostrar, use_container_width=True, hide_index=True)
    else:
        st.info("📝 No hay recurrentes registrados")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("⚙️ Generar gastos de este mes"):
            creados = app.aplicar_recurrentes_mes(sel_month)
            if creados > 0:
                st.success(f"✅ Se generaron {creados} gastos del mes")
                st.rerun()
            else:
                st.warning("No se generaron gastos (puede que ya existan o falte cuenta)")

    with col_b:
        # Activar/Desactivar por ID
        with st.form("toggle_rec"):
            st.subheader("Activar/Desactivar")
            rec_id = st.number_input("ID de recurrente", min_value=1, step=1)
            activar = st.selectbox("Estado", ["Activar", "Desactivar"])
            if st.form_submit_button("Aplicar"):
                ok = app.toggle_recurrente_activo(int(rec_id), True if activar == "Activar" else False)
                if ok:
                    st.success("Actualizado")
                    st.rerun()

    # Formulario para crear nuevo recurrente
    with st.expander("➕ Agregar nuevo recurrente"):
        with st.form("nuevo_recurrente"):
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("📝 Nombre")
                importe = st.number_input("💰 Importe", min_value=0.0, step=0.01)
                periodicidad = st.selectbox("⏱️ Periodicidad", ["Mensual"])  # Por ahora solo mensual
                dia_mes = st.number_input("📅 Día del mes", min_value=1, max_value=28, value=1)
            with col2:
                cuentas_df = app.get_cuentas_df()
                cuentas = cuentas_df['nombre'].tolist() if not cuentas_df.empty else []
                cuenta = st.selectbox("🏦 Cuenta (cargo)", cuentas) if cuentas else st.text_input("🏦 Cuenta (crear nueva)")
                categoria = st.text_input("📂 Categoría (opcional)")

            if st.form_submit_button("💾 Agregar recurrente"):
                if nombre.strip():
                    if app.add_recurrente(nombre.strip(), importe, periodicidad, int(dia_mes), cuenta, categoria or None):
                        st.success("✅ Recurrente agregado")
                        st.rerun()
                else:
                    st.error("El nombre es obligatorio")

def render_cuentas_tab(app: FinanzasApp):
    """
    Renderiza la pestaña de gestión de cuentas.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
    """
    st.header("🏦 Gestión de Cuentas")
    
    # Obtener cuentas
    cuentas_df = app.get_cuentas_df()
    
    # Mostrar resumen de cuentas
    if not cuentas_df.empty:
        total_saldo = cuentas_df['saldo_inicial'].sum()
        st.metric("💰 Saldo total en cuentas", f"€ {total_saldo:,.2f}")
        
        # Mostrar tabla de cuentas
        st.subheader("📋 Cuentas activas")
        
        # Crear DataFrame para mostrar
        display_df = cuentas_df[['nombre', 'saldo_inicial']].copy()
        display_df.columns = ['Cuenta', 'Saldo actual']
        display_df['Saldo actual'] = display_df['Saldo actual'].apply(lambda x: f"€ {x:,.2f}")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # Gráfico de saldos con ejes fijos
        st.subheader("📊 Distribución de saldos")
        
        # Selector de tipo de gráfico para cuentas
        chart_type_cuentas_tab = st.selectbox(
            "📊 Tipo de gráfico",
            ["Barras", "Circular"],
            key="chart_type_cuentas_tab"
        )
        
        if not cuentas_df.empty:
            saldos_chart = cuentas_df.set_index('nombre')['saldo_inicial']
            max_saldo = saldos_chart.max()
            chart_data = pd.DataFrame({
                'Cuenta': saldos_chart.index,
                'Saldo': saldos_chart.values
            })
            
            import altair as alt
            
            if chart_type_cuentas_tab == "Barras":
                chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X('Cuenta:N', title='Cuenta'),
                    y=alt.Y('Saldo:Q', title='Saldo (€)', scale=alt.Scale(domain=[0, max_saldo * 1.1])),
                    color=alt.value('#A8D5BA')
                ).properties(
                    height=240,
                    width='container'
                )
            else:  # Circular
                chart = alt.Chart(chart_data).mark_arc().encode(
                    theta=alt.Theta('Saldo:Q', type='quantitative'),
                    color=alt.Color('Cuenta:N', scale=alt.Scale(scheme='pastel1')),
                    tooltip=['Cuenta', alt.Tooltip('Saldo:Q', format='.2f', title='Saldo (€)')]
                ).properties(
                    height=240,
                    width='container'
                )
            
            st.altair_chart(chart, use_container_width=True)
        
    else:
        st.info("📝 No hay cuentas registradas")
    
    # Formulario para agregar cuenta
    with st.expander("➕ Agregar nueva cuenta"):
        with st.form("nueva_cuenta"):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre = st.text_input("🏦 Nombre de la cuenta")
            
            with col2:
                saldo_inicial = st.number_input(
                    "💰 Saldo inicial", 
                    min_value=0.0, 
                    step=0.01,
                    help="Saldo actual en la cuenta"
                )
            
            if st.form_submit_button("💾 Agregar cuenta"):
                if nombre.strip():
                    if app.add_cuenta(nombre.strip(), saldo_inicial):
                        st.success("✅ Cuenta agregada correctamente")
                        st.rerun()
                else:
                    st.error("❌ El nombre de la cuenta no puede estar vacío")
    
    # Actualizar saldos existentes
    if not cuentas_df.empty:
        with st.expander("✏️ Actualizar saldos"):
            st.subheader("Actualizar saldo de cuentas")
            
            for _, cuenta in cuentas_df.iterrows():
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                
                with col1:
                    st.write(f"**{cuenta['nombre']}**")
                
                with col2:
                    nuevo_saldo = st.number_input(
                        "Nuevo saldo",
                        value=float(cuenta['saldo_inicial']),
                        step=0.01,
                        key=generate_unique_key("saldo", str(cuenta['id']), "cuentas"),
                        label_visibility="collapsed",
                    )
                
                with col3:
                    if st.button("💾 Actualizar", key=generate_unique_key("update", str(cuenta['id']), "cuentas")):
                        if app.update_cuenta_saldo(cuenta['id'], nuevo_saldo):
                            st.success("✅ Saldo actualizado")
                            st.rerun()
                
                with col4:
                    if st.button("🗑️ Desactivar", key=generate_unique_key("delete", str(cuenta['id']), "cuentas")):
                        if app.delete_cuenta(cuenta['id']):
                            st.success("✅ Cuenta desactivada")
                            st.rerun()

def render_transferencias_tab(app: FinanzasApp, sel_month: date):
    """
    Renderiza la pestaña de gestión de transferencias.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
        sel_month (date): Mes seleccionado
    """
    st.header("🔄 Gestión de Transferencias")
    
    # Mostrar transferencias del mes
    transferencias_df = app.get_transferencias_df(sel_month)
    
    if not transferencias_df.empty:
        st.subheader("📋 Transferencias del mes")
        st.dataframe(transferencias_df, use_container_width=True)
        
        # Botones de exportación
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Exportar CSV"):
                csv_path = app.export_data_to_csv(transferencias_df, f"transferencias_{sel_month.strftime('%Y_%m')}")
                with open(csv_path, 'r') as f:
                    st.download_button(
                        label="💾 Descargar CSV",
                        data=f.read(),
                        file_name=f"transferencias_{sel_month.strftime('%Y_%m')}.csv",
                        mime="text/csv"
                    )
        
        with col2:
            if st.button("📊 Exportar Excel"):
                excel_path = app.export_data_to_excel(
                    {"Transferencias": transferencias_df}, 
                    f"transferencias_{sel_month.strftime('%Y_%m')}"
                )
                with open(excel_path, 'rb') as f:
                    st.download_button(
                        label="💾 Descargar Excel",
                        data=f.read(),
                        file_name=f"transferencias_{sel_month.strftime('%Y_%m')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    else:
        st.info("📝 No hay transferencias registradas para este mes")
    
    # Formulario para agregar transferencia
    with st.expander("➕ Agregar nueva transferencia"):
        with st.form("nueva_transferencia"):
            col1, col2 = st.columns(2)
            
            with col1:
                fecha = st.date_input("📅 Fecha", value=sel_month)
                
                # Obtener cuentas disponibles
                cuentas_df = app.get_cuentas_df()
                cuentas_disponibles = cuentas_df['nombre'].tolist() if not cuentas_df.empty else []
                
                if len(cuentas_disponibles) >= 2:
                    cuenta_origen = st.selectbox("🏦 Cuenta origen", cuentas_disponibles)
                    cuenta_destino = st.selectbox("🏦 Cuenta destino", cuentas_disponibles)
                else:
                    st.warning("⚠️ Necesitas al menos 2 cuentas para hacer transferencias")
                    cuenta_origen = cuenta_destino = None
            
            with col2:
                importe = st.number_input("💰 Importe", min_value=0.01, step=0.01)
                descripcion = st.text_input("📝 Descripción (opcional)")
            
            if st.form_submit_button("💾 Agregar transferencia"):
                if cuenta_origen and cuenta_destino and cuenta_origen != cuenta_destino:
                    if app.add_transferencia(fecha, cuenta_origen, cuenta_destino, importe, descripcion):
                        st.success("✅ Transferencia agregada correctamente")
                        st.rerun()
                else:
                    st.error("❌ Selecciona cuentas diferentes")



def render_sobres_tab(app: FinanzasApp, sel_month: date):
    """
    Renderiza la pestaña de presupuesto por sobres.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
        sel_month (date): Mes seleccionado
    """
    st.header("📁 Presupuesto por Sobres")
    
    # Mostrar sobres actuales
    sobres_df = app.get_sobres_df()
    
    if not sobres_df.empty:
        st.subheader("📋 Sobres activos")
        
        # Obtener cuentas disponibles para el selector
        cuentas_df = app.get_cuentas_df()
        cuentas_options = ["Sin cuenta"] + cuentas_df['nombre'].tolist() if not cuentas_df.empty else ["Sin cuenta"]
        
        # Preparar datos para la tabla editable
        editable_data = []
        for _, sobre in sobres_df.iterrows():
            cuenta_actual = sobre['cuenta_nombre'] if sobre['cuenta_nombre'] else "Sin cuenta"
            editable_data.append({
                'ID': sobre['id'],
                'Nombre': sobre['nombre'],
                'Descripción': sobre['descripcion'],
                'Objetivo (€)': sobre['importe_objetivo'],
                'Actual (€)': sobre['importe_actual'],
                'Cuenta': cuenta_actual,
                'Rollover': sobre['permite_rollover']
            })
        
        # Crear tabla editable
        edited_df = st.data_editor(
            pd.DataFrame(editable_data),
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", disabled=True),
                "Nombre": st.column_config.TextColumn("Nombre", required=True),
                "Descripción": st.column_config.TextColumn("Descripción"),
                "Objetivo (€)": st.column_config.NumberColumn("Objetivo (€)", min_value=0.0, step=10.0),
                "Actual (€)": st.column_config.NumberColumn("Actual (€)", min_value=0.0, step=10.0),
                "Cuenta": st.column_config.SelectboxColumn("Cuenta", options=cuentas_options),
                "Rollover": st.column_config.CheckboxColumn("Rollover")
            }
        )
        
        # Botón para guardar cambios
        if st.button("💾 Guardar cambios", type="primary"):
            success_count = 0
            for _, row in edited_df.iterrows():
                # Obtener cuenta_id
                cuenta_id = None
                if row['Cuenta'] != "Sin cuenta":
                    cuenta = cuentas_df[cuentas_df['nombre'] == row['Cuenta']]
                    if not cuenta.empty:
                        cuenta_id = cuenta.iloc[0]['id']
                
                # Actualizar sobre
                if app.update_sobre(
                    sobre_id=int(row['ID']),
                    nombre=row['Nombre'],
                    descripcion=row['Descripción'],
                    importe_objetivo=row['Objetivo (€)'],
                    importe_actual=row['Actual (€)'],
                    permite_rollover=row['Rollover'],
                    cuenta_id=cuenta_id
                ):
                    success_count += 1
            
            if success_count == len(edited_df):
                st.success(f"✅ {success_count} sobres actualizados correctamente")
                st.rerun()
            else:
                st.error(f"❌ Error al actualizar algunos sobres")
        
        # Gráfico de sobres
        import altair as alt
        
        chart_data = pd.DataFrame({
            'Sobre': sobres_df['nombre'],
            'Objetivo': sobres_df['importe_objetivo'],
            'Actual': sobres_df['importe_actual']
        })
        
        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('Sobre:N', title='Sobre'),
            y=alt.Y('Objetivo:Q', title='Importe (€)'),
            color=alt.value('#A8D5BA')
        ).properties(
            height=300,
            width='container'
        )
        
        st.altair_chart(chart, use_container_width=True)
        
        # Resumen de sobres
        total_objetivo = sobres_df['importe_objetivo'].sum()
        total_actual = sobres_df['importe_actual'].sum()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 Total objetivo", f"€ {total_objetivo:,.2f}")
        with col2:
            st.metric("💎 Total actual", f"€ {total_actual:,.2f}")
        with col3:
            diferencia = total_objetivo - total_actual
            st.metric("📊 Diferencia", f"€ {diferencia:,.2f}")
        
    else:
        st.info("📝 No hay sobres configurados")
    
    # Formulario para agregar sobre
    with st.expander("➕ Agregar nuevo sobre"):
        with st.form("nuevo_sobre"):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre = st.text_input("📝 Nombre del sobre")
                descripcion = st.text_input("📄 Descripción")
            
            with col2:
                importe_objetivo = st.number_input("💰 Importe objetivo mensual", min_value=0.0, step=0.01)
                
                # Selector de cuenta para nuevo sobre
                cuentas_df = app.get_cuentas_df()
                cuentas_options = ["Sin cuenta"] + cuentas_df['nombre'].tolist() if not cuentas_df.empty else ["Sin cuenta"]
                cuenta_seleccionada = st.selectbox("🏦 Cuenta asociada", cuentas_options)
                
                permite_rollover = st.checkbox("🔄 Permite rollover", value=True)
            
            if st.form_submit_button("💾 Agregar sobre"):
                if nombre.strip():
                    # Obtener cuenta_id
                    cuenta_id = None
                    if cuenta_seleccionada != "Sin cuenta":
                        cuenta = cuentas_df[cuentas_df['nombre'] == cuenta_seleccionada]
                        if not cuenta.empty:
                            cuenta_id = cuenta.iloc[0]['id']
                    
                    if app.add_sobre(nombre.strip(), descripcion, importe_objetivo, permite_rollover, cuenta_id):
                        st.success("✅ Sobre agregado correctamente")
                        st.rerun()
                else:
                    st.error("❌ El nombre del sobre no puede estar vacío")

def render_config_tab(app: FinanzasApp):
    """
    Renderiza la pestaña de configuración.
    
    Args:
        app (FinanzasApp): Instancia de la aplicación
    """
    st.header("⚙️ Configuración")
    
    config = app.config
    
    with st.form("configuracion"):
        st.subheader("🎯 Configuración de presupuesto")
        
        # Selector de moneda
        moneda = st.selectbox(
            "💱 Moneda",
            ["EUR", "USD", "GBP"],
            index=["EUR", "USD", "GBP"].index(config.get("Moneda", "EUR"))
        )
        
        # Porcentajes de presupuesto
        col1, col2, col3 = st.columns(3)
        
        with col1:
            p_ahorro = st.number_input(
                "💎 % Ahorro objetivo",
                min_value=0.0, max_value=1.0,
                value=config.get("% Ahorro objetivo", 0.25),
                step=0.01,
                help="Porcentaje de ingresos destinado al ahorro"
            )
        
        with col2:
            p_fijos = st.number_input(
                "🏠 % Fijos (necesidades)",
                min_value=0.0, max_value=1.0,
                value=config.get("% Fijos (necesidades)", 0.50),
                step=0.01,
                help="Porcentaje para gastos fijos y necesidades"
            )
        
        with col3:
            p_variables = st.number_input(
                "🎉 % Variables (deseos)",
                min_value=0.0, max_value=1.0,
                value=config.get("% Variables (deseos)", 0.25),
                step=0.01,
                help="Porcentaje para gastos variables y deseos"
            )
        
        # Validación de porcentajes
        is_valid, validation_msg = app.validate_budget_percentages(p_ahorro, p_fijos, p_variables)
        
        if not is_valid:
            st.warning(validation_msg)
            
            # Opción de auto-corrección
            if st.checkbox("🔧 Auto-corregir porcentajes"):
                p_ahorro_corr, p_fijos_corr, p_variables_corr = app.auto_correct_budget(p_ahorro, p_fijos, p_variables)
                st.info(f"Porcentajes corregidos: Ahorro {p_ahorro_corr*100:.1f}%, Fijos {p_fijos_corr*100:.1f}%, Variables {p_variables_corr*100:.1f}%")
                p_ahorro, p_fijos, p_variables = p_ahorro_corr, p_fijos_corr, p_variables_corr
        else:
            st.success(validation_msg)
        
        # Ahorro automático mensual
        st.subheader("💰 Ahorro automático")
        
        ahorro_automatico = st.number_input(
            "💎 Ahorro automático mensual (€)",
            min_value=0.0,
            value=float(config.get("Ahorro automático mensual", 500.0)),
            step=10.0,
            help="Cantidad fija que se guarda automáticamente cada mes en tu caja de ahorro"
        )
        
        # Configuración adicional
        st.subheader("🔧 Configuración adicional")
        
        col1, col2 = st.columns(2)
        with col1:
            validar_100 = st.checkbox(
                "✅ Validar presupuesto 100%", 
                value=config.get("Validar presupuesto 100%", "true").lower() == "true"
            )
        
        with col2:
            auto_corregir = st.checkbox(
                "🔧 Auto-corregir presupuesto", 
                value=config.get("Auto-corregir presupuesto", "false").lower() == "true"
            )
        
        if st.form_submit_button("💾 Guardar configuración"):
            nueva_config = {
                "Moneda": moneda,
                "% Ahorro objetivo": p_ahorro,
                "% Fijos (necesidades)": p_fijos,
                "% Variables (deseos)": p_variables,
                "Mes objetivo": config.get("Mes objetivo", date.today()),
                "Fuentes de ingreso": config.get("Fuentes de ingreso", ["Nomina"]),
                "Validar presupuesto 100%": str(validar_100).lower(),
                "Auto-corregir presupuesto": str(auto_corregir).lower(),
                "Ahorro automático mensual": ahorro_automatico
            }
            
            if app.save_config(nueva_config):
                st.success("✅ Configuración guardada correctamente")

# =============================================================================
# AUTENTICACIÓN PERSONALIZADA CON SEGURIDAD MEJORADA
# =============================================================================

import time
import json
from datetime import datetime, timedelta
from pathlib import Path

def load_user_credentials():
    """Cargar credenciales de usuarios desde config.yaml o st.secrets"""
    try:
        # Intentar cargar desde st.secrets (para deploy en cloud)
        # Solo si st.secrets está configurado correctamente
        try:
            if hasattr(st, 'secrets') and st.secrets and len(st.secrets) > 0:
                secrets_creds = st.secrets.get('credentials', {}).get('usernames', {})
                if secrets_creds:
                    return secrets_creds
        except Exception:
            # Si hay error con st.secrets, continuar con config.yaml
            pass
        
        # Intentar cargar desde archivo local
        # Probar múltiples rutas posibles
        possible_paths = [
            Path('config.yaml'),
            Path(__file__).parent / 'config.yaml',
            Path.cwd() / 'config.yaml'
        ]
        
        for config_path in possible_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r') as file:
                        config = yaml.load(file, Loader=yaml.SafeLoader)
                        local_creds = config.get('credentials', {}).get('usernames', {})
                        if local_creds:
                            return local_creds
                except Exception as e:
                    print(f"Error leyendo {config_path}: {e}")
                    continue
        
        # NO HAY FALLBACK - Fallar duro si no hay configuración
        st.error("❌ **ERROR CRÍTICO DE SEGURIDAD**")
        st.error("No se encontró archivo de configuración `config.yaml`")
        st.error("La aplicación no puede iniciar sin credenciales válidas")
        st.error("")
        st.error("**Para solucionar:**")
        st.error("1. Ejecuta: `python generate_password.py`")
        st.error("2. Crea tu archivo `config.yaml` con tus credenciales")
        st.error("3. Asegúrate de que `config.yaml` NO esté en el repositorio")
        st.stop()
        
    except Exception as e:
        st.error(f"❌ Error al cargar credenciales: {e}")
        st.error("Verifica que el archivo config.yaml sea válido")
        st.stop()

def get_login_attempts():
    """Obtener intentos de login desde session state"""
    if 'login_attempts' not in st.session_state:
        st.session_state.login_attempts = {}
    return st.session_state.login_attempts

def record_login_attempt(username: str, success: bool, ip_address: str = "unknown"):
    """Registrar intento de login para rate limiting y telemetría"""
    attempts = get_login_attempts()
    
    if username not in attempts:
        attempts[username] = {
            'failed_attempts': 0,
            'last_attempt': 0,
            'blocked_until': 0,
            'login_history': []
        }
    
    current_time = time.time()
    user_attempts = attempts[username]
    
    # Registrar en historial de telemetría
    login_record = {
        'timestamp': datetime.now().isoformat(),
        'username': username,
        'success': success,
        'ip_address': ip_address,
        'user_agent': st.get_user_agent() if hasattr(st, 'get_user_agent') else 'unknown'
    }
    
    user_attempts['login_history'].append(login_record)
    
    # Mantener solo los últimos 100 intentos para evitar memoria infinita
    if len(user_attempts['login_history']) > 100:
        user_attempts['login_history'] = user_attempts['login_history'][-100:]
    
    if success:
        # Resetear contadores en login exitoso
        user_attempts['failed_attempts'] = 0
        user_attempts['blocked_until'] = 0
        user_attempts['last_attempt'] = current_time
    else:
        # Incrementar contador de fallos
        user_attempts['failed_attempts'] += 1
        user_attempts['last_attempt'] = current_time
        
        # Aplicar bloqueo exponencial
        if user_attempts['failed_attempts'] >= 5:
            # Bloqueo de 1 minuto después de 5 intentos
            user_attempts['blocked_until'] = current_time + 60
        elif user_attempts['failed_attempts'] >= 3:
            # Bloqueo exponencial: 2^intentos segundos
            delay = 2 ** user_attempts['failed_attempts']
            user_attempts['blocked_until'] = current_time + delay

def is_user_blocked(username: str) -> tuple[bool, float]:
    """Verificar si un usuario está bloqueado y cuánto tiempo queda"""
    attempts = get_login_attempts()
    
    if username not in attempts:
        return False, 0
    
    user_attempts = attempts[username]
    current_time = time.time()
    
    if current_time < user_attempts['blocked_until']:
        remaining_time = user_attempts['blocked_until'] - current_time
        return True, remaining_time
    
    return False, 0

def get_login_telemetry() -> dict:
    """Obtener estadísticas de telemetría de login"""
    attempts = get_login_attempts()
    stats = {
        'total_users': len(attempts),
        'total_attempts': 0,
        'successful_logins': 0,
        'failed_logins': 0,
        'blocked_users': 0,
        'recent_activity': []
    }
    
    for username, user_data in attempts.items():
        stats['total_attempts'] += len(user_data['login_history'])
        stats['successful_logins'] += sum(1 for record in user_data['login_history'] if record['success'])
        stats['failed_logins'] += sum(1 for record in user_data['login_history'] if not record['success'])
        
        # Verificar si está bloqueado actualmente
        is_blocked, _ = is_user_blocked(username)
        if is_blocked:
            stats['blocked_users'] += 1
        
        # Agregar actividad reciente (últimas 24 horas)
        recent_records = [
            record for record in user_data['login_history']
            if datetime.fromisoformat(record['timestamp']) > datetime.now() - timedelta(hours=24)
        ]
        stats['recent_activity'].extend(recent_records)
    
    # Ordenar actividad reciente por timestamp
    stats['recent_activity'].sort(key=lambda x: x['timestamp'], reverse=True)
    
    return stats

def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verificar contraseña usando bcrypt"""
    import bcrypt
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))

def show_login_page():
    """Mostrar página de login personalizada con rate limiting y cookies"""
    # Encabezado compacto (evita ocupar toda la pantalla en móvil)
    
    # Verificar si ya está autenticado
    if 'authenticated' in st.session_state and st.session_state.authenticated:
        # Verificar expiración de sesión (30 minutos de inactividad o 7 días si hay cookie)
        if 'login_timestamp' in st.session_state:
            login_time = datetime.fromtimestamp(st.session_state.login_timestamp)
            remember_me = st.session_state.get('remember_me', False)
            
            # Duración de sesión: 30 minutos normales, 30 días si "recordar sesión"
            session_duration = timedelta(days=30) if remember_me else timedelta(minutes=30)
            
            if datetime.now() - login_time > session_duration:
                # Sesión expirada, limpiar y requerir nuevo login
                logout()
                if remember_me:
                    st.warning("⚠️ Cookie expirada. Por favor, inicia sesión nuevamente.")
                else:
                    st.warning("⚠️ Sesión expirada por inactividad. Por favor, inicia sesión nuevamente.")
                st.rerun()
        
        return True, st.session_state.user_name
    
    # Cargar credenciales (sin fallback)
    users = load_user_credentials()
    
    # Mostrar telemetría para administradores (solo si hay datos)
    telemetry = get_login_telemetry()
    if telemetry['total_attempts'] > 0:
        with st.expander("📊 Telemetría de Seguridad (Admin)"):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Intentos", telemetry['total_attempts'])
            with col2:
                st.metric("Logins Exitosos", telemetry['successful_logins'])
            with col3:
                st.metric("Logins Fallidos", telemetry['failed_logins'])
            with col4:
                st.metric("Usuarios Bloqueados", telemetry['blocked_users'])
            
            if telemetry['recent_activity']:
                st.subheader("Actividad Reciente (24h)")
                for record in telemetry['recent_activity'][:10]:  # Mostrar solo los 10 más recientes
                    status = "✅" if record['success'] else "❌"
                    time_str = datetime.fromisoformat(record['timestamp']).strftime("%H:%M:%S")
                    st.write(f"{status} {time_str} - {record['username']} ({record['ip_address']})")
    
    # Formulario de login
    with st.form("login_form"):
        st.subheader("Iniciar Sesión")
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        
        # Checkbox para "Recordar sesión"
        remember_me = st.checkbox("🔒 Recordar sesión (30 días)", value=True, 
                                 help="Mantiene la sesión activa durante 30 días")
        
        submit_button = st.form_submit_button("Entrar")
        
        if submit_button:
            # Verificar si el usuario está bloqueado
            is_blocked, remaining_time = is_user_blocked(username)
            if is_blocked:
                minutes = int(remaining_time // 60)
                seconds = int(remaining_time % 60)
                st.error(f"🚫 Usuario bloqueado por {minutes}m {seconds}s debido a múltiples intentos fallidos")
                record_login_attempt(username, False, "blocked_attempt")
                return False, None
            
            # Verificar credenciales
            if username in users:
                user_data = users[username]
                if verify_password(user_data['password'], password):
                    # Login exitoso
                    record_login_attempt(username, True, "successful_login")
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.user_name = user_data['name']
                    st.session_state.user_email = user_data['email']
                    st.session_state.login_timestamp = time.time()
                    st.session_state.remember_me = remember_me
                    
                    if remember_me:
                        st.success(f"✅ ¡Bienvenido {user_data['name']}! Sesión guardada por 30 días.")
                    else:
                        st.success(f"✅ ¡Bienvenido {user_data['name']}!")
                    
                    st.rerun()
                else:
                    # Contraseña incorrecta
                    record_login_attempt(username, False, "wrong_password")
                    st.error("❌ Contraseña incorrecta")
                    
                    # Mostrar información sobre bloqueo
                    attempts = get_login_attempts()
                    if username in attempts:
                        failed = attempts[username]['failed_attempts']
                        remaining = 5 - failed
                        if remaining > 0:
                            st.warning(f"⚠️ Te quedan {remaining} intentos antes del bloqueo")
                        else:
                            st.warning("⚠️ Usuario bloqueado por múltiples intentos fallidos")
            else:
                # Usuario no encontrado
                record_login_attempt(username, False, "user_not_found")
                st.error("❌ Usuario no encontrado")
    
    # Mostrar información de ayuda
    with st.expander("💡 Ayuda"):
        st.write("**Para acceder:**")
        st.write("1. Usa las credenciales configuradas en `config.yaml`")
        st.write("2. Si no tienes config.yaml, ejecuta: `python generate_password.py`")
        st.write("")
        st.write("**Seguridad:**")
        st.write("• Máximo 5 intentos fallidos antes del bloqueo")
        st.write("• Bloqueo exponencial: 2s, 4s, 8s, 16s, 60s")
        st.write("• Sesión activa: 30 minutos de inactividad")
        st.write("• Cookie: 30 días si marcas 'Recordar sesión'")
    
    return False, None

def logout():
    """Cerrar sesión"""
    for key in ['authenticated', 'username', 'user_name', 'user_email', 'remember_me']:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """
    Función principal de la aplicación.
    
    Esta función:
    1. Configura la página de Streamlit
    2. Maneja la autenticación
    3. Inicializa la aplicación de finanzas
    4. Renderiza la interfaz de usuario
    5. Maneja la navegación entre pestañas
    """
    # Configuración de la página (debe ir primero)
    st.set_page_config(
        page_title="Finanzas Personales",
        page_icon="💶",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Verificar autenticación
    auth_success, user_name = show_login_page()
    
    if not auth_success:
        st.stop()
    
    # Evitar título grande en móvil; ir directo al contenido
    
    # Botón de logout en sidebar
    with st.sidebar:
        st.write(f"👤 Bienvenido, **{user_name}**")
        if st.button("🚪 Cerrar sesión"):
            logout()
    
    # Inicializar aplicación
    app = FinanzasApp()
    
    # Renderizar sidebar y obtener mes seleccionado
    sel_month = render_sidebar(app)
    
    # Navegación por pestañas
    tab_dashboard, tab_gastos, tab_recurrentes, tab_ingresos, tab_transferencias, tab_sobres, tab_cuentas, tab_config = st.tabs([
        "📊 Panel", "💸 Gastos", "🔁 Recurrentes", "💰 Ingresos", "🔄 Transferencias", "📁 Sobres", "🏦 Cuentas", "⚙️ Configuración"
    ])
    
    # Renderizar contenido de cada pestaña
    with tab_dashboard:
        render_dashboard(app, sel_month)
    
    with tab_gastos:
        render_gastos_tab(app, sel_month)
    
    with tab_recurrentes:
        render_recurrentes_tab(app, sel_month)

    with tab_ingresos:
        render_ingresos_tab(app, sel_month)
    
    with tab_transferencias:
        render_transferencias_tab(app, sel_month)
    
    with tab_sobres:
        render_sobres_tab(app, sel_month)
    
    with tab_cuentas:
        render_cuentas_tab(app)
    
    with tab_config:
        render_config_tab(app)
    


if __name__ == "__main__":
    main()
