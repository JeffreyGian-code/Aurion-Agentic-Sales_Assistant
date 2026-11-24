from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from app.api.schemas import ChatRequest
from pydantic import ValidationError


def main():
    try:
        from app.agents.agent import build_agent
        from app.api.routes.chat import final_reply
        agent = build_agent()
    except Exception:
        print("Chat could not start. Check database and provider configuration.")
        return
    history = []
    while True:
        try:
            raw = input("You: ").strip()
            if raw.lower() == "exit":
                break
            request = ChatRequest(message=raw)
            result = agent.invoke({"messages": [*history, {"role": "user", "content": request.message}]})
            print("AI:", final_reply(result))
            history = result["messages"]
        except (EOFError, KeyboardInterrupt):
            break
        except ValidationError:
            print("Enter a message between 1 and 2000 characters.")
        except ModelCallLimitExceededError:
            print("The processing limit was reached. Try a simpler question.")
        except Exception:
            print("The assistant could not finish this request.")


if __name__ == "__main__":
    main()
