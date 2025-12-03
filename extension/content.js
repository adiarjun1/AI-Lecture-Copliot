// Content script for Google Docs interaction
(function() {
  'use strict';
  
  // Listen for messages from sidepanel
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'getDocContent') {
      // Extract text from Google Docs
      const docContent = extractDocContent();
      sendResponse(docContent);
    } else if (request.action === 'applySuggestions') {
      // Apply suggestions to the document
      applySuggestions(request.suggestions);
      sendResponse({ success: true });
    } else if (request.action === 'highlightMisconceptions') {
      // Highlight misconceptions
      highlightMisconceptions(request.misconceptions);
      sendResponse({ success: true });
    }
    return true; // Keep channel open for async response
  });
  
  function extractDocContent() {
    // Get document ID from URL (for reference, not used for API calls)
    const urlMatch = window.location.pathname.match(/\/document\/d\/([a-zA-Z0-9-_]+)/);
    const docId = urlMatch ? urlMatch[1] : null;
    
    // Extract text content from Google Docs DOM
    // Google Docs uses a complex DOM structure with nested spans
    // Try multiple selectors to find the main content area
    const selectors = [
      '.kix-page-content-wrapper',
      '[contenteditable="true"]',
      '.kix-appview-editor',
      '#kix-app'
    ];
    
    let editableArea = null;
    for (const selector of selectors) {
      editableArea = document.querySelector(selector);
      if (editableArea) break;
    }
    
    let text = '';
    if (editableArea) {
      // Get all text nodes from the editable area
      const walker = document.createTreeWalker(
        editableArea,
        NodeFilter.SHOW_TEXT,
        null,
        false
      );
      
      let node;
      let lastText = '';
      while (node = walker.nextNode()) {
        const nodeText = node.textContent.trim();
        // Avoid duplicate consecutive text
        if (nodeText && nodeText !== lastText) {
          text += nodeText + '\n';
          lastText = nodeText;
        }
      }
    } else {
      // Fallback: get text from body
      text = document.body.innerText || document.body.textContent || '';
    }
    
    return {
      docId: docId,
      text: text.trim()
    };
  }
  
  function applySuggestions(suggestions) {
    // Insert suggestions using DOM manipulation (MVP approach)
    // Suggestions are inserted as visually distinct inline elements
    suggestions.forEach(suggestion => {
      // Find insertion point based on context
      const insertionPoint = findInsertionPoint(suggestion.context || '');
      if (insertionPoint) {
        insertSuggestion(insertionPoint, suggestion.text);
      } else {
        // If no context match, append to end of document
        appendSuggestionToEnd(suggestion.text);
      }
    });
  }
  
  function appendSuggestionToEnd(text) {
    // Append suggestion to the end of the document
    const selectors = [
      '.kix-page-content-wrapper',
      '[contenteditable="true"]',
      'body'
    ];
    
    for (const selector of selectors) {
      const container = document.querySelector(selector);
      if (container) {
        const suggestionSpan = document.createElement('span');
        suggestionSpan.textContent = '\n' + text;
        suggestionSpan.style.backgroundColor = '#f0f0f0';
        suggestionSpan.style.color = '#666';
        suggestionSpan.style.padding = '2px 4px';
        suggestionSpan.style.borderRadius = '2px';
        suggestionSpan.className = 'ai-suggestion';
        suggestionSpan.style.display = 'block';
        suggestionSpan.style.marginTop = '8px';
        
        container.appendChild(suggestionSpan);
        break;
      }
    }
  }
  
  function findInsertionPoint(context) {
    // Simple text matching to find where to insert
    // In production, use semantic similarity
    const allText = document.body.innerText;
    const contextIndex = allText.indexOf(context);
    if (contextIndex !== -1) {
      // Find the DOM node at this position
      return findNodeAtPosition(contextIndex);
    }
    return null;
  }
  
  function findNodeAtPosition(position) {
    // Simplified: find text node at character position
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      null,
      false
    );
    
    let currentPos = 0;
    let node;
    while (node = walker.nextNode()) {
      if (currentPos + node.textContent.length >= position) {
        return node;
      }
      currentPos += node.textContent.length;
    }
    return null;
  }
  
  function insertSuggestion(node, text) {
    // Insert suggestion with light gray background as inline element
    const span = document.createElement('span');
    span.textContent = ' [' + text + '] ';
    span.style.backgroundColor = '#f0f0f0';
    span.style.color = '#666';
    span.style.padding = '2px 4px';
    span.style.borderRadius = '2px';
    span.style.fontStyle = 'italic';
    span.className = 'ai-suggestion';
    span.setAttribute('data-ai-suggestion', 'true');
    
    // Insert after the node
    if (node && node.parentNode) {
      // Try to insert after the node
      if (node.nextSibling) {
        node.parentNode.insertBefore(span, node.nextSibling);
      } else {
        node.parentNode.appendChild(span);
      }
    }
  }
  
  function highlightMisconceptions(misconceptions) {
    misconceptions.forEach(misconception => {
      // Find and highlight the misconception text
      const text = misconception.text;
      highlightText(text, '#fff3e0', misconception.suggestion);
    });
  }
  
  function highlightText(searchText, backgroundColor, comment) {
    // Highlight misconceptions using DOM manipulation (MVP approach)
    // Search in the main content area
    const selectors = [
      '.kix-page-content-wrapper',
      '[contenteditable="true"]',
      'body'
    ];
    
    let searchArea = null;
    for (const selector of selectors) {
      searchArea = document.querySelector(selector);
      if (searchArea) break;
    }
    
    if (!searchArea) return;
    
    const walker = document.createTreeWalker(
      searchArea,
      NodeFilter.SHOW_TEXT,
      null,
      false
    );
    
    let node;
    let found = false;
    while ((node = walker.nextNode()) && !found) {
      const nodeText = node.textContent;
      const index = nodeText.indexOf(searchText);
      
      if (index !== -1 && node.parentNode) {
        const before = nodeText.substring(0, index);
        const match = nodeText.substring(index, index + searchText.length);
        const after = nodeText.substring(index + searchText.length);
        
        const parent = node.parentNode;
        
        // Create text nodes and highlight span
        const beforeNode = document.createTextNode(before);
        const matchSpan = document.createElement('span');
        matchSpan.textContent = match;
        matchSpan.style.backgroundColor = backgroundColor;
        matchSpan.style.borderLeft = '3px solid #ff9800';
        matchSpan.style.padding = '2px 4px';
        matchSpan.style.borderRadius = '2px';
        matchSpan.className = 'ai-misconception';
        matchSpan.setAttribute('data-ai-misconception', 'true');
        matchSpan.title = 'Possible misconception: ' + (comment || 'Check this statement');
        
        // Add a comment-like tooltip
        matchSpan.addEventListener('mouseenter', function() {
          showTooltip(this, comment);
        });
        
        const afterNode = document.createTextNode(after);
        
        // Replace the original node with the split nodes
        parent.replaceChild(beforeNode, node);
        parent.insertBefore(matchSpan, beforeNode.nextSibling);
        parent.insertBefore(afterNode, matchSpan.nextSibling);
        
        found = true;
        break;
      }
    }
  }
  
  function showTooltip(element, text) {
    // Simple tooltip display (can be enhanced)
    if (text) {
      element.setAttribute('title', 'Possible misconception: ' + text);
    }
  }
})();

