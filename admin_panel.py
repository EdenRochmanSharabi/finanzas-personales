#!/usr/bin/env python3
"""
Panel de Administración para Finanzas Personales
Permite ver telemetría de login y gestionar sesiones activas
"""

import streamlit as st
import yaml
import time
from datetime import datetime, timedelta
from pathlib import Path
import json

def load_user_credentials():
    """Cargar credenciales de usuarios"""
    try:
        # Intentar cargar desde st.secrets (para deploy en cloud)
        try:
            if hasattr(st, 'secrets') and st.secrets and len(st.secrets) > 0:
                secrets_creds = st.secrets.get('credentials', {}).get('usernames', {})
                if secrets_creds:
                    st.success("✅ Credenciales cargadas desde Streamlit Secrets")
                    return secrets_creds
        except Exception as e:
            st.info(f"ℹ️ No se encontraron credenciales en Streamlit Secrets: {e}")
        
        # Intentar cargar desde archivo local
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
                            st.success(f"✅ Credenciales cargadas desde {config_path}")
                            return local_creds
                        else:
                            st.warning(f"⚠️ Archivo {config_path} existe pero no contiene credenciales válidas")
                except Exception as e:
                    st.error(f"❌ Error leyendo {config_path}: {e}")
                    continue
            else:
                st.info(f"ℹ️ Archivo no encontrado: {config_path}")
        
        st.error("❌ No se encontraron credenciales en ninguna ubicación")
        return {}
        
    except Exception as e:
        st.error(f"❌ Error al cargar credenciales: {e}")
        return {}

def get_login_telemetry():
    """Obtener telemetría de login desde session state"""
    if 'login_attempts' not in st.session_state:
        return {
            'total_attempts': 0,
            'successful_logins': 0,
            'failed_logins': 0,
            'blocked_users': 0,
            'recent_activity': []
        }
    
    attempts = st.session_state.login_attempts
    total_attempts = 0
    successful_logins = 0
    failed_logins = 0
    blocked_users = 0
    recent_activity = []
    
    # Calcular estadísticas
    for username, user_data in attempts.items():
        total_attempts += user_data.get('failed_attempts', 0)
        
        # Contar logins exitosos y fallidos del historial
        for record in user_data.get('login_history', []):
            if record.get('success', False):
                successful_logins += 1
            else:
                failed_logins += 1
            
            # Actividad reciente (últimas 24 horas)
            try:
                record_time = datetime.fromisoformat(record.get('timestamp', ''))
                if datetime.now() - record_time < timedelta(hours=24):
                    recent_activity.append(record)
            except:
                pass
        
        # Contar usuarios bloqueados
        if user_data.get('blocked_until', 0) > time.time():
            blocked_users += 1
    
    return {
        'total_attempts': total_attempts,
        'successful_logins': successful_logins,
        'failed_logins': failed_logins,
        'blocked_users': blocked_users,
        'recent_activity': sorted(recent_activity, key=lambda x: x.get('timestamp', ''), reverse=True)
    }

def get_active_sessions():
    """Obtener sesiones activas"""
    if 'active_sessions' not in st.session_state:
        st.session_state.active_sessions = {}
    
    # Limpiar sesiones expiradas
    current_time = time.time()
    active_sessions = {}
    
    for session_id, session_data in st.session_state.active_sessions.items():
        login_time = session_data.get('login_timestamp', 0)
        remember_me = session_data.get('remember_me', False)
        
        # Duración de sesión
        session_duration = 30 * 24 * 60 * 60 if remember_me else 30 * 60  # 30 días o 30 minutos
        
        if current_time - login_time < session_duration:
            active_sessions[session_id] = session_data
    
    st.session_state.active_sessions = active_sessions
    return active_sessions

def force_logout_user(username):
    """Forzar logout de un usuario específico"""
    if 'active_sessions' not in st.session_state:
        return False
    
    # Buscar y eliminar sesiones del usuario
    sessions_to_remove = []
    for session_id, session_data in st.session_state.active_sessions.items():
        if session_data.get('username') == username:
            sessions_to_remove.append(session_id)
    
    for session_id in sessions_to_remove:
        del st.session_state.active_sessions[session_id]
    
    return len(sessions_to_remove) > 0

def main():
    """Panel de administración principal"""
    st.set_page_config(
        page_title="Admin Panel - Finanzas Personales",
        page_icon="🔧",
        layout="wide"
    )
    
    st.title("🔧 Panel de Administración")
    st.markdown("---")
    
    # Verificar si el usuario es administrador
    users = load_user_credentials()
    if not users:
        st.warning("⚠️ No se encontraron credenciales configuradas")
        st.info("💡 Para usar el panel de administración:")
        st.write("1. Asegúrate de tener config.yaml configurado")
        st.write("2. O ejecuta: `python generate_streamlit_secrets.py`")
        st.write("3. O configura las credenciales en Streamlit Cloud")
        st.stop()
    
    # Mostrar información de usuarios registrados
    st.subheader("👥 Usuarios Registrados")
    user_cols = st.columns(len(users))
    
    for i, (username, user_data) in enumerate(users.items()):
        with user_cols[i]:
            st.metric(
                label=f"Usuario: {username}",
                value=user_data.get('name', 'Sin nombre'),
                delta=user_data.get('email', 'Sin email')
            )
    
    st.markdown("---")
    
    # Telemetría de login
    st.subheader("📊 Telemetría de Login")
    telemetry = get_login_telemetry()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Intentos", telemetry['total_attempts'])
    with col2:
        st.metric("Logins Exitosos", telemetry['successful_logins'])
    with col3:
        st.metric("Logins Fallidos", telemetry['failed_logins'])
    with col4:
        st.metric("Usuarios Bloqueados", telemetry['blocked_users'])
    
    # Actividad reciente
    if telemetry['recent_activity']:
        st.subheader("🕒 Actividad Reciente (24h)")
        
        # Crear tabla de actividad
        activity_data = []
        for record in telemetry['recent_activity'][:20]:  # Mostrar solo los 20 más recientes
            try:
                timestamp = datetime.fromisoformat(record.get('timestamp', ''))
                time_str = timestamp.strftime("%d/%m %H:%M:%S")
                status = "✅" if record.get('success', False) else "❌"
                username = record.get('username', 'unknown')
                ip_address = record.get('ip_address', 'unknown')
                
                activity_data.append({
                    "Hora": time_str,
                    "Estado": status,
                    "Usuario": username,
                    "IP": ip_address,
                    "Detalles": record.get('ip_address', 'N/A')
                })
            except:
                continue
        
        if activity_data:
            st.dataframe(activity_data, use_container_width=True)
    
    st.markdown("---")
    
    # Gestión de sesiones activas
    st.subheader("🔐 Gestión de Sesiones Activas")
    
    active_sessions = get_active_sessions()
    
    if active_sessions:
        st.write(f"**Sesiones activas: {len(active_sessions)}**")
        
        # Crear tabla de sesiones
        sessions_data = []
        for session_id, session_data in active_sessions.items():
            login_time = datetime.fromtimestamp(session_data.get('login_timestamp', 0))
            time_str = login_time.strftime("%d/%m %H:%M:%S")
            username = session_data.get('username', 'unknown')
            remember_me = session_data.get('remember_me', False)
            session_type = "30 días" if remember_me else "30 min"
            
            sessions_data.append({
                "Usuario": username,
                "Login": time_str,
                "Tipo": session_type,
                "ID Sesión": session_id[:8] + "..."
            })
        
        if sessions_data:
            st.dataframe(sessions_data, use_container_width=True)
            
            # Botones para forzar logout
            st.subheader("🚪 Forzar Logout")
            user_options = list(set([session.get('username') for session in active_sessions.values()]))
            
            if user_options:
                selected_user = st.selectbox("Seleccionar usuario para desconectar:", user_options)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"🔌 Desconectar {selected_user}"):
                        if force_logout_user(selected_user):
                            st.success(f"✅ Usuario {selected_user} desconectado exitosamente")
                            st.rerun()
                        else:
                            st.error(f"❌ No se pudo desconectar al usuario {selected_user}")
                
                with col2:
                    if st.button("🔌 Desconectar TODOS"):
                        st.session_state.active_sessions = {}
                        st.success("✅ Todos los usuarios han sido desconectados")
                        st.rerun()
    else:
        st.info("ℹ️ No hay sesiones activas en este momento")
    
    st.markdown("---")
    
    # Información del sistema
    st.subheader("⚙️ Información del Sistema")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Configuración actual:**")
        st.write(f"• Usuarios registrados: {len(users)}")
        st.write(f"• Sesiones activas: {len(active_sessions)}")
        st.write(f"• Intentos de login: {telemetry['total_attempts']}")
    
    with col2:
        st.write("**Seguridad:**")
        st.write("• Rate limiting activo")
        st.write("• Bloqueo exponencial")
        st.write("• Telemetría de login")
        st.write("• Gestión de sesiones")
    
    # Exportar datos
    st.markdown("---")
    st.subheader("📤 Exportar Datos")
    
    if st.button("📄 Exportar Telemetría (JSON)"):
        telemetry_json = json.dumps(telemetry, indent=2, default=str)
        st.download_button(
            label="⬇️ Descargar telemetría",
            data=telemetry_json,
            file_name=f"telemetria_finanzas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

if __name__ == "__main__":
    main()
