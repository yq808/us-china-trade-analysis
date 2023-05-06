import sys
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import calendar
import re
import math

### needed for analysis
import matplotlib.pyplot as plt
import statsmodels.api as sm
from scipy.stats import pearsonr
import numpy as np
import seaborn as sns

# compiling all trade csv datasets into one, and reorganizing the structure
def compile_data(folder) :
    print("Compiling all starting CSV datasets together.")

    csv_files = []

    for file in os.listdir(folder):
        if file.endswith('.csv'):
            file = os.path.join(folder, file)
            csv_files.append(file)

    data_concat = pd.concat([ pd.read_csv(f) for f in csv_files ], ignore_index=True)

    cols_to_keep = ['RefPeriodId', 'FlowDesc', 'PrimaryValue']
    new_data = data_concat[cols_to_keep]

    new_data = new_data.sort_values(by='RefPeriodId')
    
    df_pivot = pd.pivot_table(new_data, 
                              values='PrimaryValue', 
                              index=['RefPeriodId'], 
                              columns=['FlowDesc'], 
                              aggfunc='sum')

    df_pivot.columns = ["".join(col).strip() for col in df_pivot.columns.values]

    df_pivot = df_pivot.reset_index()

    df_pivot = df_pivot.rename(columns={
        'Export': 'ExportValue', 
        'Import': 'ImportValue',
    })

    print("Done compiling!\n")
    
    return df_pivot

# calculations for change in export and change in import
def calculate_export_import_change(df) :
    print("Calculating export and import changes from trade information.")

    index = df.index[0]
    
    df['ExportPrevious'] = df['ExportValue'].shift(1)
    df['ImportPrevious'] = df['ImportValue'].shift(1)
    df.loc[0:index, ['ExportPrevious']] = [0]
    df.loc[0:index, ['ImportPrevious']] = [0]

    df['ChangeInExport'] = round((df['ExportValue'] - df['ExportPrevious']) / df['ExportPrevious'] * 100, 3)
    df['ChangeInImport'] = round((df['ImportValue'] - df['ImportPrevious']) / df['ImportPrevious'] * 100, 3)
    
    for i, value in enumerate(df['ChangeInExport']):
        if math.isinf(value):
            df.loc[0:i, ['ChangeInExport']] = [0]
            
    for i, value in enumerate(df['ChangeInImport']):
        if math.isinf(value):
            df.loc[0:i, ['ChangeInImport']] = [0]

    df = df.drop(['ExportPrevious', 'ImportPrevious'], axis=1)

    print("Done calculating.")

    return df

# API requests
def api_call(time_period, symbol) :
    url, params = get_request_params(time_period, symbol)

    # if API unresponsive
    try :
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
    except :
        print("API request failed.")
        return None
    result = response.json()
    
    exchange_rate = result['response']['rates'][symbol]
    
    return exchange_rate

def get_request_params(time_period, symbol) :
    year = time_period[:4]
    month = time_period[4:6]
    day = time_period[6:]
    date = year + "-" + month + "-" + day
    
    url = "https://api.currencybeacon.com/v1/historical"
    params = {
        'api_key' : '',
        'base' : 'USD',
        'date' : date,
        'symbols' : symbol
    }
    return url, params

# getting exchange rate data from API and calculating change in exchange rate
def get_exchange_rate(df, symbol) :
    index = df.index[0]

    # testing if API unresponsive
    if api_call("20220801", symbol) is None:
        return None

    df['ExchangeRate'] = round(df['RefPeriodId'].apply(lambda time_period: api_call(str(time_period), symbol)), 3)

    df['ExchangeRatePrevious'] = df['ExchangeRate'].shift(1)
    df.loc[0:index, ['ExchangeRatePrevious']] = df['ExchangeRate']

    df['ChangeInExchangeRate'] = round((df['ExchangeRate'] - df['ExchangeRatePrevious']) / df['ExchangeRatePrevious'] * 100, 3)

    df = df.drop(['ExchangeRatePrevious'], axis=1)
    
    return df

# web scraping The New York Times for number of articles
def get_news_from(time_period, country) :
    year = time_period[:4]
    month = time_period[4:6]
    start_date = time_period

    num_days = calendar.monthrange(int(year), int(month))[1]
    end_date = year + month + str(num_days)

    url = "https://www.nytimes.com/search?dropmab=false&endDate=" + end_date + "&query=us%20" + country.lower() + "%20trade&sort=best&startDate=" + start_date
    
    content = requests.get(url)
    soup = BeautifulSoup(content.content, 'html.parser')
    
    pattern = "\d+"
    status = soup.find('p', {"data-testid": "SearchForm-status"})
    num_results = re.findall(pattern, status.text.split(':')[0])[0]

    return num_results

# actually performing web scraping
def get_news(df, country) :
    df['ArticlesWritten'] = df['RefPeriodId'].apply(lambda time_period: get_news_from(str(time_period), country))
    df['ArticlesWritten'] = pd.to_numeric(df['ArticlesWritten'])
    
    return df

# merging three dataframes from three sources into one!
def merge_df(df1, df2, df3) :
    print("Merging all data into one dataset.")
    df = pd.merge(df1, df2, on='RefPeriodId')
    df = pd.merge(df, df3, on='RefPeriodId')

    df['RefPeriodId'] = pd.to_datetime(df['RefPeriodId'], format='%Y%m%d')
    
    return df



# analysis
def line_graph(df) :
    sns.set_style("whitegrid")
    
    print("Creating line graph for export value and import value for 2010-2022.")

    columns_to_plot = ['ExportValue', 'ImportValue']

    plt.figure(figsize=(10, 8))

    for col in columns_to_plot:
        plt.plot(df['RefPeriodId'], df[col], label=col)

    plt.title('Export and Import Values Over Time')
    plt.xlabel('Date')
    plt.ylabel('Value (USD)')

    plt.xticks(df['RefPeriodId'][::12], rotation=45)
    plt.legend()
    
    save_path = os.path.join("visualization_imgs/line_graph.png")
    plt.savefig(save_path)
    print("Done creating graph.")
    print("Graph saved to", save_path, "\n")
    plt.show()

def pearsons_correl(df_modified) :
    x = df_modified['ChangeInExchangeRate']
    y = df_modified['ArticlesWritten']

    corr_coef, p_value = pearsonr(x, y)
    print("\nPearson's correlation between exchange rate change and articles written:", corr_coef, "\tp-value:", round(p_value, 4))

    X = sm.add_constant(x)

    model = sm.OLS(y, X).fit()

    print(model.summary())

    return corr_coef, p_value

def regression_analysis(df, name="") :
    print("\nPerforming linear regression analysis with the variables of exchange rate change and articles written.")
    df_modified = df.copy()
    df_modified['ChangeInExchangeRate'] = abs(df_modified['ChangeInExchangeRate'])
    
    corr_coef, p_value = pearsons_correl(df_modified)
    
    a, b = np.polyfit(df_modified['ChangeInExchangeRate'], df_modified['ArticlesWritten'], 1)

    plt.figure(figsize=(10, 8))

    plt.scatter(df_modified['ChangeInExchangeRate'], df_modified['ArticlesWritten'], color="lightseagreen")

    # line of best fit
    plt.plot(df_modified['ChangeInExchangeRate'], a*df_modified['ChangeInExchangeRate']+b, color="pink")

    # regression equation
    plt.text(3, 100, 'y = ' + '{:.3f}'.format(b) + ' + {:.3f}'.format(a) + 'x', size=16)

    plt.xlabel('Exchange Rate Change (absolute values)')
    plt.ylabel('Articles Written')
    plt.title("Linear Regression for Exchange Rate Change and Articles Written")

    save_path = os.path.join("visualization_imgs/regression_analysis" + name + ".png")
    plt.savefig(save_path)
    print("Done with analysis!")
    print("\nGraph saved to", save_path, "\n")
    plt.show()

    return corr_coef, p_value

def histogram_distribution(df, column_name, title) :
    print("Creating histogram distribution for", column_name)
    data = df[column_name]

    plt.hist(data)
    plt.title(title)
    plt.ylabel('Frequency')
    plt.xlabel(column_name + " (%)")

    save_path = os.path.join("visualization_imgs/histogram_" + column_name.lower() + ".png")
    plt.savefig(save_path)
    print("Graph saved to", save_path, "\n")
    plt.show()
    
def evaluation_metrics() :
    print("\n***********")
    print("Since the correlation between change in exchange rate and articles written was significant, we are applying the same data collection and linear regression analysis to a new sample to see if the trend is consistent between US and Mexico trade.")

    data_mxn = compile_data("datasets/evaluation_metrics")
    df_trade_mxn = calculate_export_import_change(data_mxn)
    
    df_api_mxn = data_mxn.loc[:,['RefPeriodId']].copy()
    df_web_mxn = data_mxn.loc[:,['RefPeriodId']].copy()

    print("\nQuerying exchange rate API for the first of each month from 2010-2022.")
    print("This should take around 3 minutes.")
    df_exchange_rate_mxn = get_exchange_rate(df_api_mxn, "MXN")
    if df_exchange_rate_mxn is None :
        print("Using backup exchange_rates_mxn.csv file instead.")
        df_exchange_rate_mxn = pd.read_csv("datasets/exchange_rates_mxn.csv")
    else :
        print("Done querying!")
    df_exchange_rate_mxn.to_csv("datasets/exchange_rates_mxn.csv", index=False, encoding='utf-8-sig')
    print("\nSize of dataset obtained from API requests:", df_exchange_rate_mxn.shape)
    print("Sample API data:\n", df_exchange_rate_mxn.head(n=5))

    print("\nStarting scraping the number of New York Times articles with keyword 'US Mexico Trade' within each month from 2010-2022.")
    print("This should take around 2 minutes.")
    df_news_mxn = get_news(df_web_mxn, "Mexico")
    print("Done scraping.")
    print("\nSize of dataset obtained from web scraping:", df_news_mxn.shape)
    print("Sample web scraping data:\n", df_news_mxn.head(n=5), "\n")

    df_mxn = merge_df(df_trade_mxn, df_exchange_rate_mxn, df_news_mxn)
    df_mxn.to_csv("datasets/trade_data_mxn.csv", index=False, encoding='utf-8-sig')

    print("\nSize of the final dataset obtained:", df_mxn.shape)

    corr_coef, p_value = regression_analysis(df_mxn, name="evaluation_metric")

    return corr_coef, p_value

def analyze_data(df) :
    print("\n***********")
    print("Data collected. Now performing statistical analysis and visualizations for the resulting dataset.\n")

    line_graph(df)
    
    histogram_distribution(df, "ChangeInExport", "Distribution of Export Change Values")
    histogram_distribution(df, "ChangeInImport", "Distribution of Import Change Values")
    histogram_distribution(df, "ChangeInExchangeRate", "Distribution of Exchange Rate Change Values")
    
    corr_coef, p_value = regression_analysis(df)
    
    print("\nPerforming linear regression analysis with the variables of export change and exchange rate change")
    x = df['ChangeInExport']
    y = df['ChangeInExchangeRate']
    corr_coef, p_value = pearsonr(x, y)
    print("Pearson's correlation between export value change and exchange rate change:", corr_coef, "\tp-value:", round(p_value, 4))
    X = sm.add_constant(x)
    model = sm.OLS(y, X).fit()
    print(model.summary())
    
    print("\nPerforming linear regression analysis with the variables of import change and exchange rate change")
    x = df['ChangeInImport']
    y = df['ChangeInExchangeRate']
    corr_coef, p_value = pearsonr(x, y)
    print("Pearson's correlation between import value change and exchange rate change:", corr_coef, "\tp-value:", round(p_value, 4))
    X = sm.add_constant(x)
    model = sm.OLS(y, X).fit()
    print(model.summary())

    print("\nOnly the relationship between exchange rate change and articles written was significant.")

    return corr_coef, p_value

def default_function() :
    data = compile_data("datasets/uncomtrade_datasets")
    data.to_csv("datasets/compiled_trade_data.csv", index=False, encoding='utf-8-sig')
    df_trade = calculate_export_import_change(data)
    
    df_api = data.loc[:,['RefPeriodId']].copy()
    df_web = data.loc[:,['RefPeriodId']].copy()

    print("\nQuerying exchange rate API for the first of each month from 2010-2022.")
    print("This should take around 3 minutes.")
    df_exchange_rate = get_exchange_rate(df_api, "CNY")
    if df_exchange_rate is None :
        print("Using backup exchange_rates.csv file instead.")
        df_exchange_rate = pd.read_csv("datasets/exchange_rates.csv")
    else :
        print("Done querying!")
    print("\nSize of dataset obtained from API requests:", df_exchange_rate.shape)
    print("Sample API data:\n", df_exchange_rate.head(n=5))

    print("\nStarting scraping the number of New York Times articles with keyword 'US China Trade' within each month from 2010-2022.")
    print("This should take around 2 minutes.")
    df_news = get_news(df_web, "China")
    print("Done scraping.")
    print("\nSize of dataset obtained from web scraping:", df_news.shape)
    print("Sample web scraping data:\n", df_news.head(n=5), "\n")

    df = merge_df(df_trade, df_exchange_rate, df_news)
    df.to_csv("datasets/dsci_510_dataset.csv", index=False, encoding='utf-8-sig')

    print("\nSize of the final dataset obtained:", df.shape)

    # descriptive stats
    print("Actual size of the dataset obtained:", df.shape)
    print("Mean of export value:", df['ExportValue'].mean())
    print("Mean of import value:", df['ImportValue'].mean())
    print("Mean of exchange rate:", df['ExchangeRate'].mean())
    print("Mean of articles written:", df['ArticlesWritten'].mean())

    df_sorted = df.sort_values(by='ChangeInExchangeRate', ascending=False)
    print("Displaying top 5 months with the highest change in exchange rate:\n", df_sorted.head(n=5))

    # analysis
    corr_coef1, p_value1 = analyze_data(df)
    
    # evaluation metric for us mexico trade
    corr_coef2, p_value2 = evaluation_metrics()

    print("Comparison between the results from the data and evaluation metrics:")
    print("coefficient from data:", corr_coef1, "\tp-value from data:", p_value1)
    print("coefficient from evaluation metric:", corr_coef2, "\tp-value from evaluation metric:", p_value2)

    print("\nAll done!")

def scrape_function() :
    data = compile_data("datasets/uncomtrade_datasets")
    print("Performing scraping and requesting of data from the 5 most recent months available...\n")
    data = data.tail(n=5+1).reset_index()
    data = data.drop('index', axis=1)

    df_trade = calculate_export_import_change(data)
    df_trade = df_trade[1:]

    df_api = data.loc[:,['RefPeriodId']].copy()
    df_web = data.loc[:,['RefPeriodId']].copy()
    df_web.drop(index=df_web.index[0], axis=0, inplace=True)

    print("\nQuerying exchange rate API for the first of each month.")
    print("This should take around 15 seconds.")
    df_exchange_rate = get_exchange_rate(df_api, "CNY")
    if df_exchange_rate is None :
        print("Using backup exchange_rates.csv file instead.")
        df_exchange_rate = pd.read_csv("datasets/exchange_rates.csv")
        df_exchange_rate = df_exchange_rate.tail(n=5)
    else :
        df_exchange_rate = df_exchange_rate[1:]
        print("Done querying!")
    print("\nAPI data obtained:\n", df_exchange_rate)

    print("\nStarting scraping the number of New York Times articles with keyword 'US China Trade' within the given monthly periods.")
    print("This should take a few seconds.")
    df_news = get_news(df_web, "China")
    print("Done scraping.")
    print("\nWeb scraping data obtained:\n", df_news, "\n")

    df = merge_df(df_trade, df_exchange_rate, df_news)

    print("\nFinal results from scrape mode:\n", df)

    print("\nAll done!")

def static_function(path) :
    df =  pd.read_csv(path)

    print("Actual size of the dataset obtained:", df.shape)
    print("Mean of export value:", df['ExportValue'].mean())
    print("Mean of import value:", df['ImportValue'].mean())
    print("Mean of exchange rate:", df['ExchangeRate'].mean())
    print("Mean of articles written:", df['ArticlesWritten'].mean())
    print("\nPrinting data for the last 5 lines, which are the most recent months in the dataset:")
    print(df.tail(n=5))
    
    corr_coef1, p_value1 = analyze_data(df)
    
    df_mxn = pd.read_csv("datasets/trade_data_mxn.csv")
    corr_coef2, p_value2 = regression_analysis(df_mxn, name="evaluation_metric")

    print("Comparison between the results from the data and evaluation metrics:")
    print("coefficient from data:", corr_coef1, "\tp-value from data:", p_value1)
    print("coefficient from evaluation metric:", corr_coef2, "\tp-value from evaluation metric:", p_value2)
    
    print("\nAll done!")

if __name__ == '__main__' :
    if len(sys.argv) == 1 :
        # default mode
        default_function()
        # df = pd.read_csv("datasets/dsci_510_dataset.csv")
        # analyze_data(df)
    elif sys.argv[1] == '--scrape' :
        # scrape mode
        scrape_function()
    elif sys.argv[1] == '--static' :
        # static mode
        path = sys.argv[2]
        static_function(path)