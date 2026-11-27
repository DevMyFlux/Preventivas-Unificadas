import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, buildQuery, del, download, get, mensagemDeErro, patch, post, setCsrfToken, setUnauthorizedHandler } from './http';

function resposta(status: number, corpo: unknown, headers: Record<string, string> = {}) {
  const texto = typeof corpo === 'string' ? corpo : JSON.stringify(corpo);
  return new Response(status === 204 ? null : texto, { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

describe('camada HTTP', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    setCsrfToken('');
    setUnauthorizedHandler(null);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('buildQuery ignora vazios/falsos e junta listas com vírgula', () => {
    expect(buildQuery({ a: '1', b: '', c: undefined, d: null, e: false, f: true, g: ['x', 'y'], h: 0 }))
      .toBe('?a=1&f=true&g=x%2Cy&h=0');
    expect(buildQuery({})).toBe('');
    expect(buildQuery(undefined)).toBe('');
  });

  it('envia cookies da mesma origem e NÃO manda CSRF em GET', async () => {
    setCsrfToken('tok');
    fetchMock.mockResolvedValue(resposta(200, { ok: true }));
    await get('/api/x', { q: '1' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/x?q=1');
    expect(init.credentials).toBe('same-origin');
    expect(init.headers['X-CSRF-Token']).toBeUndefined();
  });

  it.each([['POST', post], ['PATCH', patch]] as const)('%s inclui o token CSRF e o corpo JSON', async (_m, fn) => {
    setCsrfToken('abc123');
    fetchMock.mockResolvedValue(resposta(200, { ok: true }));
    await fn('/api/y', { campo: 1 });
    const init = fetchMock.mock.calls[0][1];
    expect(init.headers['X-CSRF-Token']).toBe('abc123');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(init.body).toBe('{"campo":1}');
  });

  it('DELETE também leva o token CSRF', async () => {
    setCsrfToken('zzz');
    fetchMock.mockResolvedValue(resposta(200, {}));
    await del('/api/z', { a: '1' });
    expect(fetchMock.mock.calls[0][1].headers['X-CSRF-Token']).toBe('zzz');
  });

  it('erro de API vira ApiError com mensagem, código e campo do servidor', async () => {
    fetchMock.mockResolvedValue(resposta(400, { erro: 'Senha curta', codigo: 'validacao', campo: 'password' }));
    const err = await post('/api/auth/password', {}).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 400, message: 'Senha curta', codigo: 'validacao', campo: 'password' });
  });

  it('corpo de erro que não é JSON cai numa mensagem genérica', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 }));
    const err = await get('/api/x').catch((e) => e);
    expect(err).toMatchObject({ status: 502, message: 'Erro 502' });
  });

  it('401 dispara o tratador global de sessão expirada (exceto quando pedido para pular)', async () => {
    const aoExpirar = vi.fn();
    setUnauthorizedHandler(aoExpirar);
    fetchMock.mockResolvedValue(resposta(401, { erro: 'Autenticação necessária.' }));
    await get('/api/x').catch(() => {});
    expect(aoExpirar).toHaveBeenCalledTimes(1);
    await post('/api/auth/login', {}, { skipUnauthorized: true }).catch(() => {});
    expect(aoExpirar).toHaveBeenCalledTimes(1);   // login inválido não conta como sessão expirada
  });

  it('falha de rede vira ApiError com status 0 e mensagem amigável', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const err = await get('/api/x').catch((e) => e);
    expect(err).toMatchObject({ status: 0, codigo: 'rede' });
    expect(mensagemDeErro(err)).toMatch(/conexão/i);
  });

  it('cancelamento (AbortError) não é tratado como erro de rede', async () => {
    const abort = Object.assign(new Error('abortado'), { name: 'AbortError' });
    fetchMock.mockRejectedValue(abort);
    await expect(get('/api/x')).rejects.toMatchObject({ name: 'AbortError' });
    expect(mensagemDeErro(abort, 'padrão')).toBe('padrão');
  });

  it('download extrai o nome do arquivo do Content-Disposition e dispara o clique', async () => {
    fetchMock.mockResolvedValue(new Response(new Blob(['x']), {
      status: 200, headers: { 'Content-Disposition': 'attachment; filename=hmb_preventivas_20261001_20261031.xlsx' },
    }));
    const criar = vi.fn(() => 'blob:fake');
    const revogar = vi.fn();
    vi.stubGlobal('URL', { createObjectURL: criar, revokeObjectURL: revogar });
    const clique = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const nome = await download('GET', '/api/x/exportar', { a: '1' }, 'padrao.xlsx');
    expect(nome).toBe('hmb_preventivas_20261001_20261031.xlsx');
    expect(clique).toHaveBeenCalled();
    expect(revogar).toHaveBeenCalledWith('blob:fake');
    clique.mockRestore();
  });

  it('download usa o nome padrão quando o servidor não informa e propaga erros', async () => {
    fetchMock.mockResolvedValueOnce(new Response(new Blob(['x']), { status: 200 }));
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:1', revokeObjectURL: () => {} });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    expect(await download('GET', '/api/x', undefined, 'padrao.xlsx')).toBe('padrao.xlsx');
    fetchMock.mockResolvedValueOnce(resposta(403, { erro: 'Você não tem acesso.' }));
    await expect(download('GET', '/api/x', undefined, 'p.xlsx')).rejects.toMatchObject({ status: 403 });
  });
});
