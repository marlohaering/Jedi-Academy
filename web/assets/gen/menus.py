"""Small patches to Raven's menu scripts so they fit the placeholder content."""


def generate(existing):
    out = {}
    main = existing['ui/main.menu']
    main = main.decode('latin-1') if isinstance(main, bytes) else main
    patched = main.replace('open\t\t\tnewgamefirstMenu', 'exec\t\t\t"map academy"')
    assert patched != main, 'main.menu new-game action not found'
    out['ui/main.menu'] = patched
    return out
