Bridge between **Gestión de seguros** (``insurance_management``) and the
Enterprise **Documents** app (``documents``). It installs automatically when
both modules are present (also on the update of ``insurance_management``).

* Every file attached to a policy or a claim (Documents tab, upload wizard
  or chatter) also becomes a document of the **Insurance** folder of the
  Documents app, with the tag *Insurance policy* or *Insurance claim* and
  the insurer as contact. The document stays linked to its policy or claim.
* On install, the files attached before are added the same way.
* The folder is **restricted**: only its members and the Documents system
  administrators see it. Insurance users keep seeing every file from the
  policies and claims, without any Documents right.
* Moving a document to the trash in Documents keeps the file on the policy;
  deleting it for good deletes it from the policy too.
