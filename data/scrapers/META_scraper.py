import importlib.util
import os

import pandas as pd
from haystack.database.elasticsearch import ElasticsearchDocumentStore
from haystack.retriever.elasticsearch import ElasticsearchRetriever
from scrapy.crawler import CrawlerProcess

PATH = os.getcwd()
RESULTS = []


class Pipeline(object):

    questionsOnly = True

    def filter(self, item, index):
        question = item['question'][index].strip()
        if self.questionsOnly and not question.endswith("?"):
            return False
        if len(item['answer'][index].strip()) == 0:
            return False
        return True

    def process_item(self, item, spider):
        if len(item['question']) == 0:
            print("WARNING: Scraper '"+spider.name+"' provided zero results!")
            return
        validatedItems = {}
        for key, values in item.items():
            validatedItems[key] = []
        for i in range(len(item['question'])):
            if not self.filter(item, i):
                continue
            for key, values in item.items():
                validatedItems[key].append(values[i])
        if len(validatedItems['question']) == 0:
            print("WARNING: Scraper '"+spider.name+"' provided zero results after filtering!")
            return
        df = pd.DataFrame.from_dict(validatedItems)
        RESULTS.append(df)


if __name__ == "__main__":
    crawler_files = [f for f in os.listdir(PATH) if os.path.isfile(os.path.join(PATH, f)) and "META" not in f]
    process = CrawlerProcess({
        'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
        'ITEM_PIPELINES': {'__main__.Pipeline': 1}
    })
    for crawler in crawler_files:
        scraper_spec = importlib.util.spec_from_file_location("CovidScraper", crawler)
        scraper = importlib.util.module_from_spec(scraper_spec)
        scraper_spec.loader.exec_module(scraper)
        CovidScraper = scraper.CovidScraper
        process.crawl(CovidScraper)
    process.start()
    dataframe = pd.concat(RESULTS)

    MODEL = "bert-base-uncased"
    GPU = False

    document_store = ElasticsearchDocumentStore(
        host="localhost",
        username="",
        password="",
        index="document",
        text_field="answer",
        embedding_field="question_emb",
        embedding_dim=768,
        excluded_meta_data=["question_emb"],
    )

    retriever = ElasticsearchRetriever(document_store=document_store, embedding_model=MODEL, gpu=GPU)

    dataframe.fillna(value="", inplace=True)
    # Index to ES
    docs_to_index = []
    doc_id = 1

    for idx, row in list(dataframe.iterrows()):
        d = row.to_dict()
        d = {k: v.strip() for k, v in d.items()}
        d["document_id"] = idx
        # add embedding
        question_embedding = retriever.create_embedding(row["question"])
        d["question_emb"] = question_embedding
        docs_to_index.append(d)
    document_store.write_documents(docs_to_index)
