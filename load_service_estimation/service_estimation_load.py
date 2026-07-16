import schedule
import time
import logging
import os
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

last_success_date = None
RETRY_MINUTES = int(os.environ.get("ESTIMATOR_RETRY_MINUTES", 10))


def job():
    global last_success_date
    logging.info("=" * 50)
    logging.info("Memulai estimasi Load harian...")
    try:
        import importlib
        import main
        importlib.reload(main)
        row_count, target_date = main.run()
        if row_count != 1440:
            raise ValueError(f"Output load harus 1440 baris, diterima {row_count}")
        if target_date != datetime.now().date():
            raise ValueError(f"Tanggal output load {target_date} bukan hari ini")
        last_success_date = target_date
        logging.info("Estimasi Load selesai.")
    except Exception as e:
        logging.error(f"Error estimasi Load: {e}")
        import traceback
        traceback.print_exc()
    logging.info("=" * 50)


def retry_if_needed():
    if last_success_date != datetime.now().date():
        job()

def main():
    logging.info("Service Estimation Load dimulai...")
    job()
    schedule.every().day.at("00:10").do(job)
    schedule.every(RETRY_MINUTES).minutes.do(retry_if_needed)
    logging.info(f"Scheduler aktif; retry gagal setiap {RETRY_MINUTES} menit")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
