# Finanzas Personales - Aplicación Web

Una aplicación completa de gestión de finanzas personales desarrollada con Streamlit y SQLAlchemy. Permite el seguimiento de gastos, ingresos, transferencias, inversiones y análisis financiero en tiempo real.

## 🚀 Características Principales

- **Gestión completa de finanzas**: Gastos, ingresos, transferencias, inversiones
- **Base de datos SQLite**: Almacenamiento robusto y eficiente
- **Migración desde Excel**: Importa datos desde archivos Excel existentes
- **Análisis en tiempo real**: KPIs, gráficos y métricas financieras
- **Presupuesto inteligente**: Sistema 50/30/20 con seguimiento automático
- **Categorización**: Organiza transacciones con categorías y etiquetas
- **Interfaz moderna**: Diseño limpio y responsive con Streamlit
- **Autenticación segura**: Sistema de login con contraseñas hasheadas

## 📋 Requisitos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)

## 🛠️ Instalación Local

1. **Clona el repositorio**:
   ```bash
   git clone https://github.com/tu-usuario/finanzas-personales.git
   cd finanzas-personales
   ```

2. **Crea un entorno virtual**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instala las dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configura la aplicación**:
   ```bash
   cp config.example.yaml config.yaml
   ```
   Edita `config.yaml` con tus datos personales.

5. **Ejecuta la aplicación**:
   ```bash
   streamlit run app.py
   ```

## 🔧 Configuración

### Archivo config.yaml

Copia `config.example.yaml` a `config.yaml` y personaliza:

```yaml
credentials:
  usernames:
    tu_usuario:
      email: tu_email@ejemplo.com
      name: Tu Nombre Completo
      password: $2b$12$hash_generado_con_generate_password.py
```

### Generar contraseña segura

Usa el script incluido para generar contraseñas hasheadas:

```bash
python generate_password.py
```

## 🚀 Deploy en Streamlit Community Cloud

1. **Sube tu código a GitHub** (asegúrate de que `config.yaml` esté en `.gitignore`)

2. **Ve a [share.streamlit.io](https://share.streamlit.io)**

3. **Conecta tu repositorio de GitHub**

4. **Configura las variables de entorno**:
   - En la sección "Advanced settings" añade:
     - `STREAMLIT_SERVER_PORT`: `8501`
     - `STREAMLIT_SERVER_ADDRESS`: `0.0.0.0`

5. **Deploy**

### Variables de entorno para producción

Para el deploy en Streamlit Cloud, configura las credenciales como variables de entorno:

```bash
# En Streamlit Cloud > Advanced settings
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
```

## 📁 Estructura del Proyecto

```
finanzas-personales/
├── app.py                 # Aplicación principal
├── database.py            # Modelos y gestión de BD
├── migrate.py             # Migración desde Excel
├── generate_password.py   # Generador de contraseñas
├── security_check.py      # Verificación de seguridad
├── requirements.txt       # Dependencias
├── config.example.yaml    # Configuración de ejemplo
├── .gitignore            # Archivos a ignorar
├── README.md             # Este archivo
└── SECURITY.md           # Información de seguridad
```

## 🔒 Seguridad

- Las contraseñas se almacenan hasheadas con bcrypt
- La base de datos local no se sube a GitHub
- El archivo `config.yaml` está excluido del control de versiones
- Todas las transacciones financieras se mantienen privadas

## 📊 Funcionalidades

### Gestión de Transacciones
- **Gastos**: Registro con categorías, etiquetas y tipos
- **Ingresos**: Seguimiento de fuentes de ingresos
- **Transferencias**: Movimientos entre cuentas
- **Inversiones**: Seguimiento de cartera de inversión

### Análisis y Reportes
- **KPIs en tiempo real**: Ahorro, gastos, ingresos netos
- **Gráficos interactivos**: Evolución temporal, distribución
- **Presupuesto 50/30/20**: Seguimiento automático de objetivos
- **Exportación**: Datos en Excel y CSV

### Gestión de Datos
- **Migración desde Excel**: Importa datos existentes
- **Backup automático**: Respaldos de la base de datos
- **Categorización**: Sistema flexible de categorías y etiquetas

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

## 🆘 Soporte

Si encuentras algún problema o tienes sugerencias:

1. Revisa la documentación
2. Busca en los issues existentes
3. Crea un nuevo issue con detalles del problema

## 🔄 Actualizaciones

Para mantener tu aplicación actualizada:

```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

---

**Nota**: Esta aplicación está diseñada para uso personal. Nunca subas información financiera real a repositorios públicos.

