"""
DAG для анализа рынка недвижимости Мельбурна
Вариант задания: 6

Автор: Давидченко Елена 
Дата: 2025
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.dates import days_ago
import os
import shutil
import pandas as pd

# --- Конфигурация DAG ---
default_args = {
    'owner': 'student',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

dag = DAG(
    'melbourne_housing_analysis',
    default_args=default_args,
    description='Анализ рынка недвижимости Мельбурна',
    schedule_interval=timedelta(days=1),
    catchup=False,
    tags=['etl', 'melbourne_housing', 'kaggle', 'variant_5']
)

# --- Extract ---
def extract_from_kaggle(**context):
    """
    Скачивание данных о недвижимости Мельбурна с Kaggle
    """
    
    import os
    import shutil
    import kagglehub
    
    print("Начинаем извлечение данных о недвижимости Мельбурна с Kaggle...")
    

    DATA_DIR = '/opt/airflow/dags/data'
    os.makedirs(DATA_DIR, exist_ok=True)
    
    kaggle_json_path = '/home/airflow/.kaggle/kaggle.json'
    if not os.path.exists(kaggle_json_path):
        raise FileNotFoundError(f"Файл kaggle.json не найден в {kaggle_json_path}.")
    print(f"kaggle.json найден в: {kaggle_json_path}")


    dataset_name = "dansbecker/melbourne-housing-snapshot"
    print(f"Скачиваем датасет: {dataset_name}")


    path = kagglehub.dataset_download(dataset_name)
    print(f"Данные скачааны в: {path}")
    
    source_file = os.path.join(path, "melb_data.csv")
    dest_file = os.path.join(DATA_DIR, "melb_data.csv")
    shutil.copy2(source_file, dest_file)
    print(f"Файл скопирован в: {dest_file}")


    context['task_instance'].xcom_push(key='data_file_path', value=dest_file)
    print(f"Данные сохранены в: {dest_file}")
    return dest_file




def load_raw_to_postgres(**context):
    """
    Load Raw: Загрузка сырых данных в PostgreSQL
    """

    import pandas as pd

    print("Начинаем загрузку сырых данных в PostgreSQL...")                             
    data_file_path = context['task_instance'].xcom_pull(key='data_file_path', task_ids='extract_from_kaggle')
    df = pd.read_csv(data_file_path)
    print(f"Загружено {len(df)} записей из файла")

    postgres_hook = PostgresHook(postgres_conn_id='analytics_postgres')

    # Выбираем нужные столбцы
    allowed_columns = ['Suburb', 'Type', 'Rooms', 'Price', 'Distance']
    df_clean = df[[col for col in allowed_columns if col in df.columns]]
    
    df_clean.rename(columns={'Distance':'distance_from_cbd'}, inplace= True)

 
    postgres_hook.run("DROP TABLE IF EXISTS raw_melbourne_housing;")
    create_table_sql = """
    CREATE TABLE raw_melbourne_housing (
        id SERIAL PRIMARY KEY,
        suburb TEXT,
        type TEXT,
        rooms INTEGER,
        price NUMERIC,
        distance_from_cbd NUMERIC,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    postgres_hook.run(create_table_sql)
    
    postgres_hook.insert_rows(
        table='raw_melbourne_housing',
        rows=df_clean.values.tolist(),
        target_fields=list(df_clean.columns)
    )
    print(f"Успешно загружено {len(df_clean)} записей в raw_melbourne_housing")


def transform_and_clean_data(**context):
    """
    Transform: Очистка данных, преобразование дат и обогащение для дашборда
    """
    import pandas as pd
    import math # Убедимся, что math импортирован

    print("Начинаем очистку, трансформацию и обогащение данных...")

    postgres_hook = PostgresHook(postgres_conn_id='analytics_postgres')

    df = postgres_hook.get_pandas_df("SELECT * FROM raw_melbourne_housing;")
    
    df.columns = df.columns.str.strip()
    
    df = df.dropna(subset=['price', 'suburb', 'type', 'rooms', 'distance_from_cbd'])

    stg_columns = ['suburb','type','rooms','price' ,'distance_from_cbd']
    df_stg = df[stg_columns]


    #  stage таблицa
    postgres_hook.run("DROP TABLE IF EXISTS stg_melbourne_housing CASCADE;")
    create_staging_table_sql = """
    CREATE TABLE stg_melbourne_housing (
        suburb TEXT,
        type TEXT,
        rooms INTEGER,
        price NUMERIC,
        distance_from_cbd NUMERIC
    );
    """
    postgres_hook.run(create_staging_table_sql)
    
    postgres_hook.insert_rows(
        table='stg_melbourne_housing',
        rows=df_stg.values.tolist(),
        target_fields= stg_columns
    )
    print(f"Успешно загружено {len(df)} записей в stg_melbourne_housing")

# --- Задачи DAG ---


extract_task = PythonOperator(
    task_id='extract_from_kaggle',
    python_callable=extract_from_kaggle,
    dag=dag
)

load_raw_task = PythonOperator(
    task_id='load_raw_to_postgres',
    python_callable=load_raw_to_postgres,
    dag=dag
)

transform_task = PythonOperator(
    task_id='transform_and_clean_data',
    python_callable=transform_and_clean_data,
    dag=dag
)

create_datamart_task = PostgresOperator(
    task_id='create_datamart',
    postgres_conn_id='analytics_postgres',
    sql='datamart_variant_6.sql',  
    dag=dag
)


extract_task >> load_raw_task >> transform_task >> create_datamart_task
  

