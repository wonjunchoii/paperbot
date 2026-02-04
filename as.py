import requests

def get_paper_info(doi):
    # OpenAlex API 엔드포인트
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # 1. Authors
            authors = [auth['author']['display_name'] for auth in data.get('authorships', [])]
            
            # 2. Journal Name
            journal = data.get('primary_location', {}).get('source', {}).get('display_name', "N/A")
            
            # 3. Abstract (OpenAlex는 인덱스 형태로 제공하므로 복원 필요)
            inv_index = data.get('abstract_inverted_index')
            abstract = "N/A"
            if inv_index:
                # 역색인 구조를 문장으로 복원
                word_counts = {}
                for word, pos_list in inv_index.items():
                    for pos in pos_list:
                        word_counts[pos] = word
                abstract = ' '.join([word_counts[i] for i in sorted(word_counts.keys())])

            return {
                "authors": authors,
                "journal": journal,
                "abstract": abstract
            }
    except Exception as e:
        return {"error": str(e)}

# 실행 예시
doi_list = ["10.1038/s41586-020-2012-7"]
for doi in doi_list:
    print(get_paper_info(doi))