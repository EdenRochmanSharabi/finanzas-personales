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

Autor: Sistema de Finanzas Personales
Fecha: 2024
"""

import streamlit as st
import pandas as pd
import numpy as np
import calendar
import io
import yaml
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from database import DatabaseManager, get_config_value, set_config_value
from database import Gasto, Ingreso, Transferencia, Recurrente, Inversion, Precio
from database import Cuenta, Categoria, Etiqueta, Config

# Importar para autenticación
import hashlib

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
    
    Attributes:
        db_manager (DatabaseManager): Gestor de la base de datos
        config (Dict[str, Any]): Configuración actual de la aplicación
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
                "Fuentes de ingreso": get_config_value(session, "Fuentes de ingreso", ["Nomina"])
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
                elif clave in ["% Ahorro objetivo", "% Fijos (necesidades)", "% Variables (deseos)"]:
                    set_config_value(session, clave, valor, "float")
                elif clave == "Mes objetivo":
                    set_config_value(session, clave, valor, "date")
                elif clave == "Fuentes de ingreso":
                    set_config_value(session, clave, ",".join(valor) if isinstance(valor, list) else valor, "list")
            
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
            bruto (float): Importe bruto
            neto (float): Importe neto
        
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
            # Ajustar saldo de la cuenta (los ingresos suman)
            try:
                cuenta_obj.saldo_inicial = float(cuenta_obj.saldo_inicial) + float(bruto if bruto else neto)
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
            return True
        except Exception as e:
            session.rollback()
            st.error(f"Error al eliminar gasto: {e}")
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
        
        # Calcular ahorro neto (ingresos - gastos fijos - gastos variables)
        ahorro_neto = ingresos_netos - gastos_fijos - gastos_variables
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
        Obtiene los bloques de presupuesto comparando objetivo vs actual.
        
        Args:
            kpis (KPIMetrics): Métricas calculadas del mes
        
        Returns:
            List[BudgetBlock]: Lista de bloques de presupuesto
        """
        return [
            BudgetBlock("Ahorro", kpis.objetivo_ahorro, kpis.ahorro_neto, 
                       kpis.objetivo_ahorro - kpis.ahorro_neto),
            BudgetBlock("Fijos", kpis.objetivo_fijos, kpis.actual_fijos,
                       kpis.objetivo_fijos - kpis.actual_fijos),
            BudgetBlock("Variables", kpis.objetivo_variables, kpis.actual_variables,
                       kpis.objetivo_variables - kpis.actual_variables)
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
            
            # Verificar columnas requeridas
            required_columns = ['Type', 'Description', 'Amount', 'Currency', 'State']
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
                    
                    # Verificar si ya existe este gasto (evitar duplicados)
                    existing_gastos = self.get_gastos_df()
                    if not existing_gastos.empty:
                        duplicate = existing_gastos[
                            (existing_gastos['descripcion'] == description) &
                            (existing_gastos['importe'] == amount) &
                            (pd.to_datetime(existing_gastos['fecha']).dt.date == fecha)
                        ]
                        if not duplicate.empty:
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
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("💰 Ingresos netos", f"€ {kpis.ingresos_netos:,.2f}")
    with col2:
        st.metric("💸 Gastos totales", f"€ {kpis.gastos_totales:,.2f}")
    with col3:
        st.metric("💎 Ahorro neto", f"€ {kpis.ahorro_neto:,.2f}")
    with col4:
        st.metric("📈 Tasa de ahorro", f"{kpis.tasa_ahorro*100:.1f}%")
    with col5:
        st.metric("🏦 Saldo total cuentas", f"€ {total_cuentas:,.2f}")
    
    # Resumen de cuentas
    if not cuentas_df.empty:
        st.subheader("🏦 Resumen de cuentas")
        col1, col2 = st.columns(2)
        
        with col1:
            # Tabla de cuentas
            display_df = cuentas_df[['nombre', 'saldo_inicial']].copy()
            display_df.columns = ['Cuenta', 'Saldo']
            display_df['Saldo'] = display_df['Saldo'].apply(lambda x: f"€ {x:,.2f}")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        with col2:
            # Selector de tipo de gráfico para cuentas
            chart_type_cuentas = st.selectbox(
                "📊 Tipo de gráfico",
                ["Barras", "Circular"],
                key="chart_type_cuentas"
            )
            
            # Gráfico de distribución de saldos
            if not cuentas_df.empty:
                saldos_chart = cuentas_df.set_index('nombre')['saldo_inicial']
                max_saldo = saldos_chart.max() if not saldos_chart.empty else 1000
                chart_data = pd.DataFrame({
                    'Cuenta': saldos_chart.index,
                    'Saldo': saldos_chart.values
                })
                
                import altair as alt
                
                if chart_type_cuentas == "Barras":
                    chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X('Cuenta:N', title='Cuenta'),
                        y=alt.Y('Saldo:Q', title='Saldo (€)', scale=alt.Scale(domain=[0, max_saldo * 1.1])),
                        color=alt.value('#A8D5BA')
                    ).properties(
                        height=220,
                        width='container'
                    )
                else:  # Circular
                    chart = alt.Chart(chart_data).mark_arc().encode(
                        theta=alt.Theta('Saldo:Q', type='quantitative'),
                        color=alt.Color('Cuenta:N', scale=alt.Scale(scheme='pastel1')),
                        tooltip=['Cuenta', alt.Tooltip('Saldo:Q', format='.2f', title='Saldo (€)')]
                    ).properties(
                        height=220,
                        width='container'
                    )
                
                st.altair_chart(chart, use_container_width=True)
    
    # Presupuesto por bloques
    st.subheader("🎯 Presupuesto por bloques")
    budget_blocks = app.get_budget_blocks(kpis)
    
    # Crear DataFrame para mostrar
    budget_df = pd.DataFrame([
        {
            'Bloque': block.nombre,
            'Objetivo': f"€ {block.objetivo:,.2f}",
            'Actual': f"€ {block.actual:,.2f}",
            'Desviación': f"€ {block.desviacion:,.2f}"
        }
        for block in budget_blocks
    ])
    
    st.dataframe(budget_df, use_container_width=True, hide_index=True)
    
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
            col1, col2, col3 = st.columns(3)
            
            with col1:
                csv_file = st.file_uploader("Seleccionar archivo CSV", type=['csv'])
            
            with col2:
                tipo_banco = st.selectbox(
                    "🏦 Tipo de banco",
                    ["Revolut", "ImaginBank", "Otro"],
                    index=0  # Revolut por defecto
                )
            
            with col3:
                cuenta_destino = st.selectbox("🏦 Cuenta destino", cuentas_disponibles)
            
            if csv_file and cuenta_destino:
                if st.button("🚀 Procesar CSV"):
                    with st.spinner("Procesando archivo..."):
                        if tipo_banco == "Revolut":
                            result = app.import_revolut_csv(csv_file, cuenta_destino)
                        elif tipo_banco == "ImaginBank":
                            st.info("🔄 Soporte para ImaginBank próximamente...")
                            st.write("Por ahora, usa la opción 'Otro' y clasifica manualmente.")
                            return
                        else:
                            st.info("🔄 Para otros bancos, usa la clasificación manual en la pestaña de gastos.")
                            return
                    
                    if 'error' in result:
                        st.error(f"❌ Error: {result['error']}")
                    elif result.get('needs_classification', False):
                        # Mostrar transacciones que necesitan clasificación
                        st.session_state.pending_classifications = result['pending_transactions']
                        st.session_state.cuenta_destino = cuenta_destino
                        st.session_state.tipo_banco = tipo_banco
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
    if not ingresos_df.empty:
        st.dataframe(ingresos_df, use_container_width=True)
    else:
        st.info("📝 No hay ingresos registrados para este mes")
    
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
                bruto = st.number_input("💰 Bruto", min_value=0.0, step=0.01)
                neto = st.number_input("💎 Neto", min_value=0.0, step=0.01)
            
            if st.form_submit_button("💾 Agregar ingreso"):
                if app.add_ingreso(fecha, cuenta, descripcion, fuente, bruto, neto):
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
                        key=f"saldo_{cuenta['id']}",
                        label_visibility="collapsed",
                    )
                
                with col3:
                    if st.button("💾 Actualizar", key=f"update_{cuenta['id']}"):
                        if app.update_cuenta_saldo(cuenta['id'], nuevo_saldo):
                            st.success("✅ Saldo actualizado")
                            st.rerun()
                
                with col4:
                    if st.button("🗑️ Desactivar", key=f"delete_{cuenta['id']}"):
                        if app.delete_cuenta(cuenta['id']):
                            st.success("✅ Cuenta desactivada")
                            st.rerun()

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
        total = p_ahorro + p_fijos + p_variables
        if total != 1.0:
            st.warning(f"⚠️ Los porcentajes suman {total*100:.1f}%. Se recomienda que sumen 100%")
        
        if st.form_submit_button("💾 Guardar configuración"):
            nueva_config = {
                "Moneda": moneda,
                "% Ahorro objetivo": p_ahorro,
                "% Fijos (necesidades)": p_fijos,
                "% Variables (deseos)": p_variables,
                "Mes objetivo": config.get("Mes objetivo", date.today()),
                "Fuentes de ingreso": config.get("Fuentes de ingreso", ["Nomina"])
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
    tab_dashboard, tab_gastos, tab_recurrentes, tab_ingresos, tab_cuentas, tab_config = st.tabs([
        "📊 Panel", "💸 Gastos", "🔁 Recurrentes", "💰 Ingresos", "🏦 Cuentas", "⚙️ Configuración"
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
    
    with tab_cuentas:
        render_cuentas_tab(app)
    
    with tab_config:
        render_config_tab(app)
    
    # Pie de página
    st.markdown("---")
    st.caption(
        "💡 **Consejo**: Usa la migración desde Excel para importar tus datos existentes. "
        "La base de datos SQL es más robusta y permite múltiples usuarios."
    )

if __name__ == "__main__":
    main()
