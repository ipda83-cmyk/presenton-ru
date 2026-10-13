import { notifyPaymentRequired } from "@/utils/billingEvents";
import {
  isChatGptAuthRequiredResponse,
  normalizeChatGptAuthMessage,
  requestChatGptReauth,
} from "@/utils/chatgptAuth";
import {
  extractApiErrorMessage,
  extractApiErrorMetadata,
  type ApiErrorResponse,
} from "@/utils/apiErrorMessages";
import { tr } from "@/utils/clientI18n";

export class ApiResponseError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly retryable: boolean;

  constructor(
    message: string,
    {
      status,
      code,
      retryable,
    }: { status: number; code?: string; retryable: boolean }
  ) {
    super(message);
    this.name = "ApiResponseError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

// API Response Handler Utility
export class ApiResponseHandler {
  static async handleResponse(response: Response, defaultErrorMessage: string): Promise<any> {
    // Handle successful responses
    if (response.ok) {
      // Handle 204 No Content responses
      if (response.status === 204) {
        return true;
      }
      
      // Try to parse JSON response
      try {
        return await response.json();
      } catch {
        // If JSON parsing fails but response is ok, return empty object
        return {};
      }
    }

    // Handle error responses
    let errorMessage = defaultErrorMessage;
    let errorData: ApiErrorResponse | null = null;
    
    try {
      errorData = await response.json();
      errorMessage = extractApiErrorMessage(
        errorData,
        defaultErrorMessage,
        response.status
      );

      if (isChatGptAuthRequiredResponse(response, errorData, errorMessage)) {
        errorMessage = normalizeChatGptAuthMessage(errorMessage);
        requestChatGptReauth({
          message: errorMessage,
          source: "api-response",
        });
      }
    } catch {
      // If JSON parsing fails, use status-based messages
      errorMessage = this.getStatusBasedErrorMessage(response.status, defaultErrorMessage);
      if (isChatGptAuthRequiredResponse(response, null, errorMessage)) {
        errorMessage = normalizeChatGptAuthMessage(errorMessage);
        requestChatGptReauth({
          message: errorMessage,
          source: "api-response",
        });
      }
    }

    if (response.status === 402) {
      // Not enough money on the balance: the top-up dialog opens wherever the user is.
      notifyPaymentRequired(errorMessage);
    }
    const metadata = extractApiErrorMetadata(errorData, response.status);
    throw new ApiResponseError(errorMessage, {
      status: response.status,
      code: metadata.code,
      retryable: metadata.retryable,
    });
  }


  static async handleResponseWithResult(response: Response, defaultErrorMessage: string): Promise<{success: boolean, message?: string}> {
    try {
      // Handle successful responses
      if (response.ok) {
        return { success: true };
      }

      // Handle error responses
      let errorMessage = defaultErrorMessage;
      
      try {
        const errorData: ApiErrorResponse = await response.json();
        errorMessage = extractApiErrorMessage(
          errorData,
          defaultErrorMessage,
          response.status
        );

        if (isChatGptAuthRequiredResponse(response, errorData, errorMessage)) {
          errorMessage = normalizeChatGptAuthMessage(errorMessage);
          requestChatGptReauth({
            message: errorMessage,
            source: "api-response-result",
          });
        }
      } catch {
        // If JSON parsing fails, use status-based messages
        errorMessage = this.getStatusBasedErrorMessage(response.status, defaultErrorMessage);
        if (isChatGptAuthRequiredResponse(response, null, errorMessage)) {
          errorMessage = normalizeChatGptAuthMessage(errorMessage);
          requestChatGptReauth({
            message: errorMessage,
            source: "api-response-result",
          });
        }
      }

      return {
        success: false,
        message: errorMessage,
      };
    } catch (error) {
      return {
        success: false,
        message: error instanceof Error ? error.message : defaultErrorMessage,
      };
    }
  }


  private static getStatusBasedErrorMessage(status: number, defaultMessage: string): string {
    switch (status) {
      case 400:
        return tr("apiErr.status400", "Bad request. Please check your input and try again.");
      case 401:
        return tr("apiErr.status401", "Unauthorized. Please log in and try again.");
      case 403:
        return tr("apiErr.status403", "Access forbidden. You don't have permission to perform this action.");
      case 404:
        return tr("apiErr.status404", "Resource not found. The requested item may have been deleted or moved.");
      case 409:
        return tr("apiErr.status409", "Conflict. The resource already exists or there's a conflict with the current state.");
      case 422:
        return tr("apiErr.status422", "Validation error. Please check your input and try again.");
      case 429:
        return tr("apiErr.status429", "Too many requests. Please wait a moment and try again.");
      case 500:
        return tr("apiErr.status500", "Internal server error. Please try again later.");
      case 502:
        return tr("apiErr.status502", "Bad gateway. The server is temporarily unavailable.");
      case 503:
        return tr("apiErr.status503", "Service unavailable. Please try again later.");
      case 504:
        return tr("apiErr.status504", "Gateway timeout. The request took too long to process.");
      default:
        return defaultMessage;
    }
  }
}

export type { ApiErrorResponse };
