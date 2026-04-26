from libb import LIBBmodel
from .prompt_orchestration.prompt_models import *
from Experiments.multi_model_ipo.miscellaneous.order_verification import *
from Experiments.multi_model_ipo.miscellaneous.csv_conversion import *
from libb.other.parse import parse_json
import pandas as pd

MODELS = ["deepseek", "gpt-4.1"]

TODAY = pd.Timestamp.now().date()


def weekly_flow(date):

    for model in MODELS:
        libb = LIBBmodel(f"Experiments/multi_model_ipo/artifacts/{model}", run_date=date)
        libb.reset_run(auto_ensure=True)
        libb.process_portfolio()
        deep_research_report, prompt = prompt_deep_research(libb)
        libb.save_deep_research(deep_research_report)

        orders_json = parse_json(deep_research_report, "ORDERS_JSON")

        filtered_orders, rejected_orders = filter_orders(orders_json)
        if rejected_orders:
            save_rejections(libb, rejected_orders)

        libb.save_orders(filtered_orders)
        libb.analyze_sentiment(deep_research_report)
    return

def daily_flow(date):
    for model in MODELS:
        libb = LIBBmodel(f"Experiments/multi_model_ipo/artifacts/{model}", run_date=date)
        libb.process_portfolio()
        daily_report, prompt = prompt_daily_report(libb)
        libb.save_additional_log("daily-prompt.txt")
        libb.analyze_sentiment(daily_report)
        libb.save_daily_update(daily_report)

        orders_json = parse_json(daily_report, "ORDERS_JSON")

        filtered_orders, rejected_orders = filter_orders(orders_json)
        if rejected_orders:
            save_rejections(libb, rejected_orders)

        libb.save_orders(filtered_orders)
    return

def main():
    day_num = TODAY.weekday()

    if day_num  == 4: # Friday
        print("Friday: Running Weekly Flow...")
        weekly_flow(TODAY)
    else:
        print("Regular Weekday: Running Daily Flow...")
        daily_flow(TODAY) # Mon-Thursday (Non trading days will be logged)
    print("Success!")


if __name__ == "__main__":
    main()