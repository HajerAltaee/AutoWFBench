FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
COPY __init__.py contracts.py state.py server.py /app/development/simspot_ui/
COPY static/ /app/development/simspot_ui/static/
EXPOSE 8765
CMD ["python", "-m", "development.simspot_ui.server", "--bind", "0.0.0.0", "--port", "8765", "--store", "/data/simspot.sqlite3"]
