import os
from operator import itemgetter

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

load_dotenv()

print("Initializing components...")

# Same embedding model as in ingestion.py: a question must live in the same space as the chunks
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
llm = ChatOpenAI(model="gpt-6.1-sol")

vectorstore = PineconeVectorStore(index_name=os.environ["INDEX_NAME"], embedding=embeddings)

retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

prompt_template = ChatPromptTemplate.from_template(
    """Réponds à la question uniquement à partir des extraits ci-dessous.
Chaque extrait commence par sa source et son numéro de page.

{context}

Question : {question}

Consignes :
- Donne une réponse précise et complète.
- Cite la source et la page de chaque information, par exemple (ai_act_fr.pdf, p. 12).
- Si les extraits ne contiennent pas la réponse, dis-le au lieu d'inventer."""
)


def format_docs(docs):
    """Format retrieved chunks into one string, each with its source and page."""
    return "\n\n".join(
        f"[{doc.metadata.get('source')}, p. {doc.metadata.get('page')}]\n{doc.page_content}"
        for doc in docs
    )


def retrieval_chain_without_lcel(query: str):
    """Simple retrieval chain without LCEL: each step is called by hand."""
    docs = retriever.invoke(query)
    context = format_docs(docs)
    messages = prompt_template.format_messages(context=context, question=query)
    response = llm.invoke(messages)
    return response.content


def create_retrieval_chain_with_lcel():
    """Same chain with LCEL. Invoke it with {"question": "..."}."""
    return (
        RunnablePassthrough.assign(context=itemgetter("question") | retriever | format_docs)
        | prompt_template
        | llm
        | StrOutputParser()
    )


if __name__ == "__main__":
    query = "Quelles pratiques d'intelligence artificielle sont interdites par le règlement ?"

    print("\n" + "=" * 70)
    print("IMPLEMENTATION 0: Raw LLM Invocation (No RAG)")
    print("=" * 70)
    print(llm.invoke([HumanMessage(content=query)]).content)

    print("\n" + "=" * 70)
    print("IMPLEMENTATION 1: Without LCEL")
    print("=" * 70)
    print(retrieval_chain_without_lcel(query))

    print("\n" + "=" * 70)
    print("IMPLEMENTATION 2: With LCEL")
    print("=" * 70)
    chain = create_retrieval_chain_with_lcel()
    print(chain.invoke({"question": query}))
