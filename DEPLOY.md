# 🚀 Guía de Deploy - Streamlit Community Cloud

Esta guía te ayudará a desplegar tu aplicación de Finanzas Personales en Streamlit Community Cloud de forma segura.

## 📋 Prerrequisitos

1. ✅ Código subido a GitHub (ya completado)
2. ✅ Archivos sensibles protegidos con `.gitignore`
3. ✅ Configuración de Streamlit optimizada

## 🔗 Conectar con GitHub

### Opción 1: Repositorio Público (Recomendado para demo)

1. Ve a [GitHub](https://github.com) y crea un nuevo repositorio
2. Nombra el repositorio: `finanzas-personales`
3. **IMPORTANTE**: Marca como **público** para Streamlit Community Cloud
4. Sigue las instrucciones de GitHub para conectar tu repositorio local

### Opción 2: Repositorio Privado (Para uso personal)

Si prefieres mantener el repositorio privado, necesitarás:
- Cuenta de Streamlit Pro (de pago)
- O usar una alternativa como Heroku/Railway

## 🔧 Configurar Streamlit Community Cloud

1. **Ve a [share.streamlit.io](https://share.streamlit.io)**

2. **Inicia sesión con GitHub**

3. **Conecta tu repositorio**:
   - Selecciona tu repositorio `finanzas-personales`
   - Branch: `main`
   - Main file path: `app.py`

4. **Configuración avanzada**:
   - En "Advanced settings" añade:
     ```
     STREAMLIT_SERVER_PORT=8501
     STREAMLIT_SERVER_ADDRESS=0.0.0.0
     ```

5. **Deploy**:
   - Haz clic en "Deploy!"
   - Espera a que se complete el proceso

## 🔐 Configurar Credenciales en Producción

### Método 1: Variables de Entorno (Recomendado)

En Streamlit Community Cloud, ve a "Advanced settings" y añade:

```
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
```

### Método 2: Archivo de Configuración

1. Crea un archivo `config.yaml` en tu máquina local
2. Usa `generate_password.py` para crear credenciales seguras
3. **NO subas este archivo a GitHub**
4. En Streamlit Cloud, usa "Secrets management" para añadir el contenido

## 🛠️ Solución de Problemas Comunes

### Error: "Unable to deploy"

**Causa**: El código no está conectado a un repositorio GitHub remoto.

**Solución**:
```bash
# En tu máquina local
git remote add origin https://github.com/tu-usuario/finanzas-personales.git
git push -u origin main
```

### Error: "Module not found"

**Causa**: Dependencias faltantes.

**Solución**:
- Verifica que `requirements.txt` esté en el repositorio
- Asegúrate de que todas las dependencias estén listadas

### Error: "Config file not found"

**Causa**: Falta archivo de configuración.

**Solución**:
- Usa variables de entorno en Streamlit Cloud
- O configura secrets management

### Error: "Database connection failed"

**Causa**: Problemas con la base de datos.

**Solución**:
- La aplicación creará automáticamente la base de datos
- Verifica permisos de escritura

## 🔒 Seguridad en Producción

### ✅ Lo que SÍ está protegido:
- `config.yaml` (excluido del repositorio)
- `finanzas.db` (base de datos local)
- `*.xlsx` (archivos Excel con datos personales)
- `venv/` (entorno virtual)

### ⚠️ Lo que debes verificar:
- Credenciales configuradas correctamente
- Variables de entorno en Streamlit Cloud
- Repositorio público (para Community Cloud)

## 📊 Monitoreo del Deploy

### Verificar el estado:
1. Ve a tu dashboard de Streamlit
2. Revisa los logs de la aplicación
3. Verifica que la aplicación esté funcionando

### Logs importantes:
- ✅ "Application startup complete"
- ✅ "Database initialized successfully"
- ✅ "Authentication system ready"

## 🔄 Actualizaciones

Para actualizar tu aplicación:

1. **Haz cambios localmente**
2. **Prueba localmente**:
   ```bash
   streamlit run app.py
   ```
3. **Sube a GitHub**:
   ```bash
   git add .
   git commit -m "Update description"
   git push origin main
   ```
4. **Streamlit se actualiza automáticamente**

## 🆘 Soporte

Si tienes problemas:

1. **Revisa los logs** en Streamlit Community Cloud
2. **Verifica la configuración** de GitHub
3. **Consulta la documentación** de Streamlit
4. **Crea un issue** en tu repositorio

## 🎉 ¡Listo!

Una vez completado el deploy:

- Tu aplicación estará disponible en: `https://tu-app.streamlit.app`
- Solo tú tendrás acceso con tus credenciales
- Los datos se mantienen privados y seguros
- Actualizaciones automáticas desde GitHub

---

**Nota**: Esta aplicación está diseñada para uso personal. Nunca subas información financiera real a repositorios públicos.
