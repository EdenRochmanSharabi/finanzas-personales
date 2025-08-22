# 🔐 Configuración de Credenciales en Streamlit Cloud

## 🎯 Solución al Problema de Autenticación

Tu aplicación está funcionando correctamente, pero necesita credenciales para el acceso. Aquí tienes la solución segura:

## 📋 Opción 1: Usar el Script Automático (Recomendado)

### Paso 1: Generar Credenciales
```bash
python generate_streamlit_secrets.py
```

Este script te pedirá:
- Usuario
- Nombre completo
- Email
- Contraseña (con validación de seguridad)

### Paso 2: Configurar en Streamlit Cloud
1. Ve a tu aplicación: https://finanzas-personales-93ans7peeudt8rsdsl26fj.streamlit.app
2. Haz clic en **"Settings"** (⚙️) en la esquina superior derecha
3. Ve a la pestaña **"Secrets"**
4. Pega el JSON que generó el script
5. Haz clic en **"Save"**

## 📋 Opción 2: Configuración Manual

Si prefieres configurar manualmente:

### Paso 1: Crear Credenciales
Usa el script existente:
```bash
python generate_password.py
```

### Paso 2: Convertir a Formato JSON
Copia tu `config.yaml` y conviértelo a este formato JSON:

```json
{
  "credentials": {
    "usernames": {
      "tu_usuario": {
        "email": "tu_email@ejemplo.com",
        "name": "Tu Nombre Completo",
        "password": "$2b$12$hash_generado_por_el_script"
      }
    }
  }
}
```

### Paso 3: Configurar en Streamlit Cloud
1. Ve a Settings > Secrets
2. Pega el JSON
3. Save

## 🔒 Seguridad Garantizada

### ✅ Lo que está protegido:
- **Credenciales**: Solo en Streamlit Cloud, no en GitHub
- **Base de datos**: Se crea automáticamente en la nube
- **Datos personales**: Nunca se suben al repositorio

### 🛡️ Características de seguridad:
- Contraseñas hasheadas con bcrypt
- Rate limiting contra ataques de fuerza bruta
- Expiración de sesión automática
- Telemetría de intentos de login

## 🚀 Después de Configurar

Una vez configuradas las credenciales:
1. La aplicación se reiniciará automáticamente
2. Podrás acceder con tu usuario y contraseña
3. Los datos se almacenarán en la nube de Streamlit
4. Tendrás acceso desde cualquier dispositivo

## 🆘 Solución de Problemas

### Error: "No se encontró archivo de configuración"
- **Causa**: No hay credenciales configuradas en Streamlit Cloud
- **Solución**: Sigue los pasos de configuración arriba

### Error: "Credenciales inválidas"
- **Causa**: Usuario o contraseña incorrectos
- **Solución**: Verifica las credenciales en Streamlit Cloud > Secrets

### Error: "Aplicación no responde"
- **Causa**: Problema temporal de Streamlit Cloud
- **Solución**: Espera unos minutos y recarga la página

## 📞 Soporte

Si tienes problemas:
1. Verifica que el JSON esté bien formateado
2. Asegúrate de que las credenciales sean correctas
3. Revisa los logs de Streamlit Cloud
4. Contacta soporte si persiste el problema

---

**¡Tu aplicación estará completamente funcional y segura!** 🔐
