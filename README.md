# Super Prototyping community

Projects people made with [Super Prototyping](https://superproto.dev), shared to browse and
remix. They are listed at [superproto.dev/community](https://superproto.dev/community) and on
the Community tab in the app.

Each project is one folder, `projects/<id>/`, named for the `id` in its `project.json`. It holds
exactly what `sp pack -o` writes: `project.json`, the project's documents, its `canvases/` and
a `thumbnail.png` of its cover. `index.json` lists them all. CI writes it after each merge, so
never edit it by hand.

## Share a project

Ask your agent to share the project to the community. The `sp-canvas` skill knows the steps,
which are these:

```sh
sp pack "My project" --check                      # fix what it reports
gh repo fork ReScienceLab/super-prototyping-community --clone
sp pack "My project" -o /tmp/package              # prints the project's id
mv /tmp/package super-prototyping-community/projects/<id>
cd super-prototyping-community
git switch -c <id> && git add projects && git commit -m "Add My project"
gh pr create
```

To update a project, pack it again and replace its folder the same way.

CI checks every pull request:

- Each project it changes passes `sp pack --check`, holds only what `sp pack -o` writes, and is
  in the folder named for its `id`.
- A new project's `author`, in `project.json`, is whoever opened the pull request.
- A change is opened by the `author` or by one of the `contributors`. Anyone else adds their
  own GitHub login to `contributors` in the same pull request.
- Only its `author` can remove a project.

A maintainer then reviews it. The review looks at quality. It is not a promise that a project is
safe: the app shows every board in a sandbox, whoever made it.

## Licence

By opening a pull request, you confirm that the work is yours to share, and that you share it
under these terms:

- The design work (boards, images, video, documents and everything else that is not code) is
  under [CC BY 4.0](LICENSE).
- Code such as `gen.py` is under the [MIT licence](LICENSE-CODE).

Either licence covers only your own work. It grants nothing in the brands, logos or products that
a clone depicts, which stay their owners'. This repo is not affiliated with them.

## Takedown

To have something removed, open a
[takedown request](https://github.com/ReScienceLab/super-prototyping-community/issues/new?template=takedown.yml)
or email yilin.jing@rescience.com. We answer within 7 days. GitHub's
[DMCA process](https://docs.github.com/en/site-policy/content-removal-policies/dmca-takedown-policy)
applies as well.
