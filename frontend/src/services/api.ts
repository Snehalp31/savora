const BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';
export async function api<T=any>(path:string, init:RequestInit={}):Promise<T>{
 const headers = new Headers(init.headers); const token=localStorage.getItem('savora_token'); if(token) headers.set('Authorization',`Bearer ${token}`); if(init.body && !(init.body instanceof FormData)) headers.set('Content-Type','application/json');
 const response=await fetch(`${BASE}${path}`,{...init,headers});
 if(!response.ok){if(response.status===401 && path!='/auth/login' && path!='/auth/me'){localStorage.removeItem('savora_token');if(window.location.pathname!='/login')window.location.assign('/login')}let message=`Request failed (${response.status})`;try{const body=await response.json();message=body.error||message;}catch{}throw new Error(message)}
 if(response.status===204)return undefined as T;return response.json();
}
export const post=(path:string,body:unknown={})=>api(path,{method:'POST',body:JSON.stringify(body)});
